import cv2
import numpy as np
import os
import pytesseract
import secrets
from services.collection_classifier import analyze_collection


PREVIEW_WEBP_QUALITY = 55
LOSSLESS_PNG_COMPRESSION = 9


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


def process_images(
    image_paths,
    tournament_id,
    seed_number,
    debug=False,
    pre_cropped_flags=None,
):
    analysis_id = secrets.token_hex(6)
    # 1. Round1〜5の自動ソート (水色のタブのX座標で判定)
    lower_cyan = np.array([70, 50, 50])
    upper_cyan = np.array([120, 255, 255])
    
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
        scale = 1080.0 / m_w
        img_res = cv2.resize(img_modal, (1080, int(m_h * scale)))
        
        # モーダル内でシアンのタブを探してY座標の基準にする
        hsv = cv2.cvtColor(img_res, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, lower_cyan, upper_cyan)
        cnts_cyan, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        y_anchor_tab = 400
        x_anchor_tab = 540  # デフォルト: 画面中央
        if cnts_cyan:
            valid_cnts = []
            modal_h = img_res.shape[0]
            y_limit = int(modal_h * 0.17)
            
            for cnt in cnts_cyan:
                x_t, y_t, w_t, h_t = cv2.boundingRect(cnt)
                if y_t < y_limit:
                    valid_cnts.append(cnt)
            
            if valid_cnts:
                c = max(valid_cnts, key=cv2.contourArea)
            else:
                c = None
                
            if c is not None:
                x_tab, y_tab, w_tab, h_tab = cv2.boundingRect(c)
                # タブの中心X座標を記録（左端ほどROUND01に近い）
                x_anchor_tab = x_tab + w_tab // 2
                y_anchor_tab = y_tab
            
        rounds_data.append({
            "path": path, 
            "img": img_res, 
            "y_tab": y_anchor_tab,
            "x_anchor": x_anchor_tab  # ラウンド判定用X座標
        })
        
    # X座標の昇順でソート（左=ROUND01 ～ 右=ROUND05）
    rounds_data.sort(key=lambda r: r["x_anchor"])
        
    # プレイヤー情報の取得 (自動抽出は廃止し、デフォルト値を返す)
    player_name = f"Player {seed_number}"
    player_icon_url = None
    
    # 2. キャラクターアイコンの切り抜き
    y_offset = 200 
    w_crop, h_crop = 160, 160
    centers = [152, 346, 540, 734, 928]
    
    # 保存先ディレクトリ
    cropped_dir = "uploads/cropped"
    os.makedirs(cropped_dir, exist_ok=True)
    
    from services.template_matcher import get_templates, predict_character
    templates = get_templates()
    
    teams = []
    
    for r_idx, r_data in enumerate(rounds_data):
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
            
            crop_stem = (
                f"crop_t{tournament_id}_s{seed_number}_{analysis_id}"
                f"_r{r_idx+1}_c{c_idx+1}"
            )
            crop_filename = f"{crop_stem}.png"
            crop_path = os.path.join(cropped_dir, crop_filename)
            cv2.imwrite(crop_path, face)
            preview_filename = f"{crop_stem}_preview.webp"
            preview_path = os.path.join(cropped_dir, preview_filename)
            preview_written = _write_preview_image(preview_path, face)
            
            # AI推論
            pred_id, conf = predict_character(face, templates, threshold=0.65)
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
                "collection_level": collection_level,
                "collection_confidence": collection_confidence,
                # Additive structured response; legacy fields above stay intact.
                "collection_analysis": collection_analysis,
            })
            
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
