import cv2
import numpy as np
import os
import pytesseract
import secrets

def process_images(image_paths, tournament_id, seed_number):
    analysis_id = secrets.token_hex(6)
    # 1. Round1〜5の自動ソート (水色のタブのX座標で判定)
    lower_cyan = np.array([75, 50, 50])
    upper_cyan = np.array([105, 255, 255])
    
    rounds_data = []
    
    for path in image_paths:
        img = cv2.imread(path)
        if img is None:
            continue
            
        # --- モーダルウィンドウ（白い背景領域）の精密検出プロセス ---
        # Cannyエッジ検出は複雑な背景（トーナメント表など）に弱いため、
        # 白色領域（高明度・低彩度）で検出する方式に変更
        hsv_detect = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # 白色に近い領域: 彩度が低く(S<50)、明度が高い(V>200)
        white_mask = cv2.inRange(hsv_detect,
            np.array([0, 0, 200]),
            np.array([180, 50, 255]))
        # 細かいノイズを除去
        kernel = np.ones((10, 10), np.uint8)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
        cnts_white, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        modal_roi = None
        if cnts_white:
            min_x, min_y = float('inf'), float('inf')
            max_x, max_y = 0, 0
            valid_found = False
            for cnt in cnts_white:
                x, y, w, h = cv2.boundingRect(cnt)
                # モーダルの断片（画面幅の10%以上の幅、かつ5%以上の高さ）を統合する
                if w > img.shape[1] * 0.1 and h > img.shape[0] * 0.05:
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x + w)
                    max_y = max(max_y, y + h)
                    valid_found = True
            
            if valid_found and (max_x - min_x) > img.shape[1] * 0.25:
                modal_roi = (min_x, min_y, max_x - min_x, max_y - min_y)
        
        if modal_roi is None:
            # フォールバック: 画面全体を使う
            modal_roi = (0, 0, img.shape[1], img.shape[0])

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
            # R（レア）キャラクターの青い背景を誤検知しないよう、
            # Y座標が上部（y < 200）にあり、幅が広い（w > 100）ものをタブとして優先する
            valid_cnts = []
            for cnt in cnts_cyan:
                x_t, y_t, w_t, h_t = cv2.boundingRect(cnt)
                if y_t < 200 and w_t > 100:
                    valid_cnts.append(cnt)
            
            if valid_cnts:
                c = max(valid_cnts, key=cv2.contourArea)
            else:
                c = max(cnts_cyan, key=cv2.contourArea)
                
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
                    "confidence": 1.0
                })
                continue
            
            crop_filename = (
                f"crop_t{tournament_id}_s{seed_number}_{analysis_id}"
                f"_r{r_idx+1}_c{c_idx+1}.png"
            )
            crop_path = os.path.join(cropped_dir, crop_filename)
            cv2.imwrite(crop_path, face)
            
            # AI推論
            pred_id, conf = predict_character(face, templates, threshold=0.65)
            
            team.append({
                "image_url": f"/api/uploads/cropped/{crop_filename}",
                "predicted_character_id": pred_id,
                "confidence": conf
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
