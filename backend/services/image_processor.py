import cv2
import numpy as np
import os
import pytesseract
import secrets
from services.collection_classifier import analyze_collection


PREVIEW_WEBP_QUALITY = 55
LOSSLESS_PNG_COMPRESSION = 9
NORMALIZED_MODAL_WIDTH = 1080
CHARACTER_CROP_CENTERS = (152, 346, 540, 734, 928)
MAX_CHARACTER_ALIGNMENT_SHIFT = 24
ROUND_TAB_LOWER_CYAN = np.array([70, 50, 50])
ROUND_TAB_UPPER_CYAN = np.array([120, 255, 255])


def write_lossless_png(path, image):
    return cv2.imwrite(
        str(path),
        image,
        [cv2.IMWRITE_PNG_COMPRESSION, LOSSLESS_PNG_COMPRESSION],
    )


def _write_preview_image(path, image):
    return cv2.imwrite(
        str(path),
        image,
        [cv2.IMWRITE_WEBP_QUALITY, PREVIEW_WEBP_QUALITY],
    )


def _extract_modal_roi(img, pre_cropped=False):
    if pre_cropped:
        return (0, 0, img.shape[1], img.shape[0])

    hsv_detect = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    white_mask = cv2.inRange(
        hsv_detect,
        np.array([0, 0, 200]),
        np.array([180, 50, 255]),
    )
    kernel = np.ones((10, 10), np.uint8)
    white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
    cnts_white, _ = cv2.findContours(
        white_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    for cnt in sorted(cnts_white, key=cv2.contourArea, reverse=True):
        x, y, width, height = cv2.boundingRect(cnt)
        if width > img.shape[1] * 0.25 and height > img.shape[0] * 0.15:
            return (x, y, width, height)
    return (0, 0, img.shape[1], img.shape[0])


def _aligned_character_centers(x_anchor, anchor_is_reliable):
    """Apply one conservative horizontal translation to all five card crops."""
    if not anchor_is_reliable:
        return CHARACTER_CROP_CENTERS, 0
    reference = min(CHARACTER_CROP_CENTERS, key=lambda center: abs(center - x_anchor))
    shift = int(x_anchor - reference)
    if abs(shift) > MAX_CHARACTER_ALIGNMENT_SHIFT:
        return CHARACTER_CROP_CENTERS, 0
    return tuple(center + shift for center in CHARACTER_CROP_CENTERS), shift


def _is_alignment_anchor_reliable(width, height, area, modal_height):
    return (
        0.12 * NORMALIZED_MODAL_WIDTH <= width <= 0.25 * NORMALIZED_MODAL_WIDTH
        and 0.04 * modal_height <= height <= 0.20 * modal_height
        and area >= 0.20 * width * height
    )


def _find_round_tab_anchor(normalized_modal):
    hsv = cv2.cvtColor(normalized_modal, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, ROUND_TAB_LOWER_CYAN, ROUND_TAB_UPPER_CYAN)
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    modal_height = normalized_modal.shape[0]
    y_limit = int(modal_height * 0.17)
    valid = [contour for contour in contours if cv2.boundingRect(contour)[1] < y_limit]
    if not valid:
        return 400, 540, False
    contour = max(valid, key=cv2.contourArea)
    x, y, width, height = cv2.boundingRect(contour)
    reliable = _is_alignment_anchor_reliable(
        width,
        height,
        cv2.contourArea(contour),
        modal_height,
    )
    return y, x + width // 2, reliable


def _find_character_card_centers(normalized_modal, global_shift, fallback_centers):
    """Use the five ROUND tab bounds as the five character-column centers."""
    gray = cv2.cvtColor(normalized_modal, cv2.COLOR_BGR2GRAY)
    height = normalized_modal.shape[0]
    tab_band = gray[:int(height * 0.22)]
    if tab_band.size == 0:
        return fallback_centers, False

    edges = cv2.Canny(tab_band, 50, 150)
    contours, _ = cv2.findContours(
        edges,
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    candidates = []
    for contour in contours:
        x, y, width, tab_height = cv2.boundingRect(contour)
        if (
            0.14 * NORMALIZED_MODAL_WIDTH <= width <= 0.22 * NORMALIZED_MODAL_WIDTH
            and 0.08 * height <= tab_height <= 0.20 * height
            and y < 0.17 * height
        ):
            candidates.append((x, x + width, x + width / 2))

    detected_pairs = []
    for expected_center in CHARACTER_CROP_CENTERS:
        expected_center += global_shift
        nearby = [
            candidate
            for candidate in candidates
            if abs(candidate[2] - expected_center) <= 35
        ]
        if not nearby:
            return fallback_centers, False
        left, right, _ = min(
            nearby,
            key=lambda candidate: abs(candidate[2] - expected_center),
        )
        detected_pairs.append((left, right))

    widths = [right - left for left, right in detected_pairs]
    centers = tuple(round((left + right) / 2) for left, right in detected_pairs)
    gaps = [centers[index + 1] - centers[index] for index in range(4)]
    if not (
        all(160 <= width <= 205 for width in widths)
        and all(185 <= gap <= 210 for gap in gaps)
        and all(80 <= center <= NORMALIZED_MODAL_WIDTH - 80 for center in centers)
    ):
        return fallback_centers, False
    return centers, True


def _resolve_round_character_centers(rounds_data):
    """Reuse ROUND01's reliable card grid for every image in the same upload."""
    if not rounds_data:
        return []

    first_round = rounds_data[0]
    first_fallback, first_shift = _aligned_character_centers(
        first_round["x_anchor"],
        first_round["alignment_anchor_is_reliable"],
    )
    first_centers, first_reliable = _find_character_card_centers(
        first_round["img"],
        first_shift,
        first_fallback,
    )
    if first_reliable:
        return [first_centers] * len(rounds_data)

    centers_by_round = []
    for round_data in rounds_data:
        fallback, global_shift = _aligned_character_centers(
            round_data["x_anchor"],
            round_data["alignment_anchor_is_reliable"],
        )
        centers, _ = _find_character_card_centers(
            round_data["img"],
            global_shift,
            fallback,
        )
        centers_by_round.append(centers)
    return centers_by_round


def process_images(
    image_paths,
    tournament_id,
    seed_number,
    debug=False,
    pre_cropped_flags=None,
    include_source_metadata=False,
    created_output_paths=None,
    crop_owner_player_id=None,
):
    analysis_id = secrets.token_hex(6)
    # 1. Round1〜5の自動ソート (水色のタブのX座標で判定)
    rounds_data = []
    
    pre_cropped_flags = pre_cropped_flags or []
    for image_index, path in enumerate(image_paths):
        img = cv2.imread(path)
        if img is None:
            continue
            
        # --- モーダルウィンドウ（白い背景領域）の精密検出プロセス ---
        # 切り出し済み画像は全体をモーダルとして扱い、二重切り出しを防ぐ。
        # 未切り出し画像は従来の白領域検出へフォールバックする。
        pre_cropped = (
            image_index < len(pre_cropped_flags)
            and bool(pre_cropped_flags[image_index])
        )
        modal_roi = _extract_modal_roi(img, pre_cropped=pre_cropped)

        m_x, m_y, m_w, m_h = modal_roi
        img_modal = img[m_y:m_y+m_h, m_x:m_x+m_w]
        
        # モーダルを 1080px 幅に正規化
        scale = NORMALIZED_MODAL_WIDTH / m_w
        img_res = cv2.resize(
            img_modal,
            (NORMALIZED_MODAL_WIDTH, int(m_h * scale)),
        )
        
        # モーダル内でシアンのタブを探し、Round順・Y位置・X補正に使う。
        y_anchor_tab, x_anchor_tab, alignment_anchor_is_reliable = (
            _find_round_tab_anchor(img_res)
        )
            
        rounds_data.append({
            "path": path, 
            "img": img_res, 
            "y_tab": y_anchor_tab,
            "source_image_index": image_index,
            "x_anchor": x_anchor_tab,  # ラウンド判定用X座標
            "alignment_anchor_is_reliable": alignment_anchor_is_reliable,
        })
        
    # X座標の昇順でソート（左=ROUND01 ～ 右=ROUND05）
    rounds_data.sort(key=lambda r: r["x_anchor"])
    centers_by_round = _resolve_round_character_centers(rounds_data)
        
    # プレイヤー情報の取得 (自動抽出は廃止し、デフォルト値を返す)
    player_name = f"Player {seed_number}"
    player_icon_url = None
    
    # 2. キャラクターアイコンの切り抜き
    y_offset = 200 
    w_crop, h_crop = 160, 160
    
    # 保存先ディレクトリ
    cropped_dir = "uploads/cropped"
    os.makedirs(cropped_dir, exist_ok=True)
    
    from services.template_matcher import get_templates, predict_character_match
    templates = get_templates()
    
    teams = []
    
    for r_idx, (r_data, centers) in enumerate(zip(rounds_data, centers_by_round)):
        img = r_data["img"]
        y_tab_r = r_data["y_tab"]
        y_crop = y_tab_r + y_offset
        
        team = []
        for c_idx, center_x in enumerate(centers):
            x_crop = int(center_x - w_crop / 2)
            
            # 画像切り抜き (境界チェック付き)
            y_start = max(0, y_crop)
            y_end = min(img.shape[0], y_crop + h_crop)
            x_start = max(0, x_crop)
            x_end = min(img.shape[1], x_crop + w_crop)
            
            face = img[y_start:y_end, x_start:x_end]
            
            if face is None or face.size == 0:
                team.append({"image_url": None, "predicted_character_id": None, "confidence": 0})
                continue
            
            # 空枠（EMPTY SLOT）の判定：全体がほぼ灰色であるかを確認
            hsv_face = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
            # 彩度(S)が80以上のピクセル数をカウント
            high_sat_pixels = np.sum(hsv_face[:, :, 1] > 80)
            
            # 彩度の高いピクセルが極端に少ない（200px未満）場合は空枠とみなす
            if high_sat_pixels < 200:
                team.append({
                    "image_url": None,
                    "predicted_character_id": 9999,
                    "confidence": 1.0,
                    "collection_level": None,
                    "collection_confidence": 1.0,
                })
                continue
            
            owner_label = (
                f"p{int(crop_owner_player_id)}"
                if crop_owner_player_id is not None
                else f"s{seed_number}"
            )
            crop_stem = f"crop_t{tournament_id}_{owner_label}_{analysis_id}_r{r_idx+1}_c{c_idx+1}"
            crop_filename = f"{crop_stem}.png"
            crop_path = os.path.join(cropped_dir, crop_filename)
            cv2.imwrite(crop_path, face)
            if created_output_paths is not None:
                created_output_paths.append(crop_path)
            preview_filename = f"{crop_stem}_preview.webp"
            preview_path = os.path.join(cropped_dir, preview_filename)
            preview_written = _write_preview_image(preview_path, face)
            if preview_written and created_output_paths is not None:
                created_output_paths.append(preview_path)
            
            # AI推論
            match = predict_character_match(face, templates, threshold=0.65)
            pred_id, conf = match.character_id, match.similarity
            collection_analysis = analyze_collection(
                face,
                debug=debug,
                debug_dir=".local/collection-debug",
                debug_prefix=f"r{r_idx+1}_c{c_idx+1}",
            )
            if collection_analysis["has_collection"]:
                level_band = collection_analysis["debug_info"]["level_band"]
                collection_level = (
                    f"{collection_analysis['rarity']}_{level_band}"
                )
            else:
                collection_level = "none"
            collection_confidence = collection_analysis["confidence"]
            
            team.append({
                "image_url": (
                    f"/api/uploads/cropped/{preview_filename}"
                    if preview_written
                    else f"/api/uploads/cropped/{crop_filename}"
                ),
                # Lossless source used only if the user corrects the character
                # and requests a template update.
                "template_source_url": f"/api/uploads/cropped/{crop_filename}",
                "predicted_character_id": pred_id,
                "confidence": conf,
                "matched_template_filename": match.matched_template_filename,
                "match_method": match.method,
                "analysis_token": analysis_id,
                "round_number": r_idx + 1,
                "position": c_idx + 1,
                "collection_level": collection_level,
                "collection_confidence": collection_confidence,
                # Additive structured response; legacy fields above stay intact.
                "collection_analysis": collection_analysis,
            })
            
        if include_source_metadata:
            for character in team:
                character["source_image_index"] = r_data["source_image_index"]
        teams.append(team)
        
    # 不足しているラウンドを補完
    while len(teams) < 5:
        teams.append([{"image_url": None} for _ in range(5)])
        
    return {
        "suggested_player_name": player_name,
        "suggested_seed": seed_number,
        "player_icon_url": player_icon_url,
        "suggested_teams": teams
    }
