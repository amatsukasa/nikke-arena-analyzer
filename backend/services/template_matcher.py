import cv2
import os
import numpy as np
from dataclasses import dataclass
from pathlib import Path
from services.collection_classifier import NORMALIZED_SIZE, collection_match_mask
from services.template_management import list_template_paths, parse_template_name

TEMPLATE_DIR = "uploads/templates"

@dataclass(frozen=True)
class TemplateCandidate:
    image: np.ndarray
    filename: str


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

    for template_path in list_template_paths(Path(TEMPLATE_DIR)):
        filename = template_path.name
        try:
            char_id = parse_template_name(filename).character_id
            img = cv2.imread(str(template_path))
            if img is not None:
                if char_id not in templates:
                    templates[char_id] = []
                templates[char_id].append(TemplateCandidate(img, filename))
        except Exception as e:
            print(f"Failed to load template {filename}: {e}")

    total = sum(len(v) for v in templates.values())
    print(f"[Template] {len(templates)} キャラ / 計 {total} 枚 読み込み完了")
    return templates


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

    for char_id, template_list in templates.items():
        char_best_score = -1.0
        char_best_filename = None

        for index, raw_candidate in enumerate(template_list):
            candidate = _candidate(raw_candidate, char_id, index)
            template_gray = prepare_character_image(candidate.image)

            # Preserve CCOEFF_NORMED scoring while removing excluded pixels
            # from both the covariance numerator and both denominators.
            max_val = masked_ccoef_normed(face_gray, template_gray, valid_mask)

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
