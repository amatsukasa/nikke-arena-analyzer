import cv2
import os
import numpy as np
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from services.collection_classifier import NORMALIZED_SIZE, collection_match_mask
from services.template_management import list_template_paths, parse_template_name, template_operation_lock

TEMPLATE_DIR = "uploads/templates"
MATCHER_ALGORITHM_VERSION = 2
TEMPLATE_CACHE_LIMIT = 2048
TEMPLATE_CACHE_MAX_BYTES = 48 * 1024 * 1024
_template_cache: OrderedDict[tuple[str, int, int, int], "TemplateCandidate"] = OrderedDict()
cv2.setNumThreads(max(1, int(os.environ.get("OPENCV_NUM_THREADS", "1"))))

@dataclass(frozen=True)
class TemplateCandidate:
    image: np.ndarray
    filename: str
    normalized: np.ndarray | None = None


@dataclass(frozen=True)
class CharacterMatch:
    character_id: int | None
    similarity: float
    matched_template_filename: str | None
    second_similarity: float
    method: str = "masked_ccoeff_normed"


def prepare_character_image(image):
    """Normalize Character artwork without baking the badge into the pixels."""
    normalized = cv2.resize(image, (NORMALIZED_SIZE, NORMALIZED_SIZE))
    return cv2.cvtColor(normalized, cv2.COLOR_BGR2GRAY)


def get_templates():
    """
    保存されているすべてのキャラクター顔テンプレートを読み込む。
    複数バリアント対応: char_{id}.png（旧形式）と char_{id}_{N:03d}.png（新形式）の両方を読む。
    戻り値: {char_id: [img1, img2, ...]} の辞書
    """
    templates: dict[int, list] = {}
    if not os.path.exists(TEMPLATE_DIR):
        return templates

    live_keys = set()
    template_root = Path(TEMPLATE_DIR)
    # Take the same lock as admin mutations so one analysis sees either the
    # complete pre-operation set or the complete post-operation set.
    with template_operation_lock(template_root.parent):
        for template_path in list_template_paths(template_root):
            filename = template_path.name
            try:
                char_id = parse_template_name(filename).character_id
                stat = template_path.stat()
                key = (str(template_path.resolve()), stat.st_mtime_ns, stat.st_size, MATCHER_ALGORITHM_VERSION)
                live_keys.add(key)
                candidate = _template_cache.get(key)
                if candidate is None:
                    img = cv2.imread(str(template_path))
                    if img is None:
                        continue
                    gray = prepare_character_image(img)
                    candidate = TemplateCandidate(img, filename, _normalized_vector(gray))
                    _template_cache[key] = candidate
                else:
                    _template_cache.move_to_end(key)
                if candidate is not None:
                    if char_id not in templates:
                        templates[char_id] = []
                    templates[char_id].append(candidate)
            except Exception as e:
                print(f"Failed to load template {filename}: {e}")

    total = sum(len(v) for v in templates.values())
    print(f"[Template] {len(templates)} キャラ / 計 {total} 枚 読み込み完了")
    for key in list(_template_cache):
        if key not in live_keys:
            _template_cache.pop(key, None)
    while (
        len(_template_cache) > TEMPLATE_CACHE_LIMIT
        or template_cache_nbytes() > TEMPLATE_CACHE_MAX_BYTES
    ):
        _template_cache.popitem(last=False)
    return templates


def invalidate_template_cache() -> None:
    with template_operation_lock(Path(TEMPLATE_DIR).parent):
        _template_cache.clear()


def template_cache_size() -> int:
    return len(_template_cache)


def template_cache_nbytes() -> int:
    """Return bytes held by cached NumPy buffers (excluding Python overhead)."""
    return sum(
        candidate.image.nbytes
        + (candidate.normalized.nbytes if candidate.normalized is not None else 0)
        for candidate in _template_cache.values()
    )


def _candidate(candidate, char_id: int, index: int) -> TemplateCandidate:
    if isinstance(candidate, TemplateCandidate):
        return candidate
    return TemplateCandidate(candidate, f"char_{char_id}_candidate_{index:03d}.png")


def masked_ccoef_normed(first: np.ndarray, second: np.ndarray, valid_mask: np.ndarray) -> float:
    """Pearson correlation over valid pixels only (TM_CCOEFF_NORMED semantics)."""
    valid = valid_mask.astype(bool)
    first_values = first[valid].astype(np.float64).reshape(-1)
    second_values = second[valid].astype(np.float64).reshape(-1)
    if not first_values.size or first_values.size != second_values.size:
        return -1.0
    first_values -= first_values.mean()
    second_values -= second_values.mean()
    denominator = np.linalg.norm(first_values) * np.linalg.norm(second_values)
    if denominator == 0:
        return 1.0 if np.array_equal(first[valid], second[valid]) else 0.0
    return float(np.dot(first_values, second_values) / denominator)


def _normalized_vector(gray: np.ndarray) -> np.ndarray:
    valid = collection_match_mask(gray.shape).astype(bool)
    values = gray[valid].astype(np.float32).reshape(-1)
    values -= values.mean()
    norm = np.linalg.norm(values)
    return values / norm if norm else values


def masked_absolute_similarity(first: np.ndarray, second: np.ndarray, valid_mask: np.ndarray) -> float:
    """Legacy absolute-difference similarity, excluding invalid pixels entirely."""
    valid = valid_mask.astype(bool)
    if not np.any(valid):
        return 0.0
    difference = cv2.absdiff(first, second)
    return 1.0 - float(difference[valid].mean() / 255.0)


def predict_character_match(face_img, templates: dict, threshold=0.65, min_margin=0.03):
    """
    切り抜かれた顔画像とすべてのテンプレートを比較し、最も類似度が高いキャラクターIDを返す。
    複数バリアント対応: キャラごとに全バリアントを試し、最高スコアを採用する。
    """
    if not templates or face_img is None:
        return CharacterMatch(None, 0.0, None, -1.0)

    scores_by_character = []

    # グレースケールに変換
    face_gray = prepare_character_image(face_img)
    valid_mask = collection_match_mask(face_gray.shape)
    face_vector = _normalized_vector(face_gray)

    for char_id, template_list in templates.items():
        char_best_score = -1.0
        char_best_filename = None

        for index, raw_candidate in enumerate(template_list):
            candidate = _candidate(raw_candidate, char_id, index)
            template_vector = candidate.normalized
            if template_vector is None:
                template_vector = _normalized_vector(prepare_character_image(candidate.image))
            if not face_vector.size or face_vector.size != template_vector.size:
                max_val = -1.0
            elif not np.any(face_vector) or not np.any(template_vector):
                max_val = masked_ccoef_normed(face_gray, prepare_character_image(candidate.image), valid_mask)
            else:
                max_val = float(np.dot(face_vector, template_vector))

            # このキャラの最高スコアを更新
            if max_val > char_best_score:
                char_best_score = max_val
                char_best_filename = candidate.filename

        scores_by_character.append((char_best_score, char_id, char_best_filename))

    if not scores_by_character:
        return CharacterMatch(None, 0.0, None, -1.0)

    scores_by_character.sort(reverse=True)
    best_score, best_match_id, best_filename = scores_by_character[0]
    second_score = scores_by_character[1][0] if len(scores_by_character) > 1 else -1.0

    # 最高点でも、別キャラとの差が小さい場合は誤確定せず確認を促す。
    if best_score >= threshold and best_score - second_score >= min_margin:
        return CharacterMatch(best_match_id, float(best_score), best_filename, float(second_score))

    return CharacterMatch(None, float(best_score), best_filename, float(second_score))


def predict_character(face_img, templates: dict, threshold=0.65, min_margin=0.03):
    """Backward-compatible tuple API used by existing callers and tests."""
    match = predict_character_match(face_img, templates, threshold, min_margin)
    return match.character_id, match.similarity
