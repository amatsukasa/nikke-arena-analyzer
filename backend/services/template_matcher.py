import cv2
import os
import numpy as np

TEMPLATE_DIR = "uploads/templates"

def get_templates():
    """
    保存されているすべてのキャラクター顔テンプレートを読み込む。
    複数バリアント対応: char_{id}.png（旧形式）と char_{id}_{N:03d}.png（新形式）の両方を読む。
    戻り値: {char_id: [img1, img2, ...]} の辞書
    """
    templates: dict[int, list] = {}
    if not os.path.exists(TEMPLATE_DIR):
        return templates

    for filename in sorted(os.listdir(TEMPLATE_DIR)):
        if not (filename.startswith("char_") and filename.endswith(".png")):
            continue
        try:
            # char_{id}.png または char_{id}_{N}.png のどちらにも対応
            parts = filename[:-4].split("_")  # ["char", "id"] or ["char", "id", "N"]
            char_id = int(parts[1])
            filepath = os.path.join(TEMPLATE_DIR, filename)
            img = cv2.imread(filepath)
            if img is not None:
                if char_id not in templates:
                    templates[char_id] = []
                templates[char_id].append(img)
        except Exception as e:
            print(f"Failed to load template {filename}: {e}")

    total = sum(len(v) for v in templates.values())
    print(f"[Template] {len(templates)} キャラ / 計 {total} 枚 読み込み完了")
    return templates


def predict_character(face_img, templates: dict, threshold=0.65, min_margin=0.03):
    """
    切り抜かれた顔画像とすべてのテンプレートを比較し、最も類似度が高いキャラクターIDを返す。
    複数バリアント対応: キャラごとに全バリアントを試し、最高スコアを採用する。
    """
    if not templates or face_img is None:
        return None, 0.0

    scores_by_character = []

    # グレースケールに変換
    face_gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)

    for char_id, template_list in templates.items():
        char_best_score = -1.0

        for template_img in template_list:
            template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)

            # テンプレートが入力画像より大きい場合はリサイズ
            if template_gray.shape[0] > face_gray.shape[0] or template_gray.shape[1] > face_gray.shape[1]:
                template_gray = cv2.resize(template_gray, (face_gray.shape[1], face_gray.shape[0]))

            # テンプレートマッチング
            res = cv2.matchTemplate(face_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)

            # このキャラの最高スコアを更新
            if max_val > char_best_score:
                char_best_score = max_val

        scores_by_character.append((char_best_score, char_id))

    if not scores_by_character:
        return None, 0.0

    scores_by_character.sort(reverse=True)
    best_score, best_match_id = scores_by_character[0]
    second_score = scores_by_character[1][0] if len(scores_by_character) > 1 else -1.0

    # 最高点でも、別キャラとの差が小さい場合は誤確定せず確認を促す。
    if best_score >= threshold and best_score - second_score >= min_margin:
        return best_match_id, float(best_score)

    return None, float(best_score)
