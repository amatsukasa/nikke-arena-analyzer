import cv2
import numpy as np
import pytesseract

def extract_match_results(img_path):
    """
    勝敗結果のスクリーンショットから、各ラウンドの勝敗を解析する。

    新アルゴリズム（ブロブ検出ベース）:
      1. モーダルウィンドウ（白背景）を検出
      2. 水色(WIN)と赤色(LOSE)の色領域を抽出し、面積が一定以上の塊（ブロブ）を検出
      3. ブロブのY座標でグループ化し、下部にある5つのグループを5ラウンドと特定
      4. 各グループ内で水色・赤色の重心X座標を比較し、左右どちらがWINかを判定

    戻り値: {
        "rounds": [
            {"round": 1, "left": "WIN", "right": "LOSE"},
            ...
        ],
        "winner": "left" or "right"
    }
    """
    img = cv2.imread(img_path)
    if img is None:
        raise ValueError("Image not found")

    orig_h, orig_w = img.shape[:2]
    target_w = 1080
    target_h = int(orig_h * target_w / orig_w)
    img = cv2.resize(img, (target_w, target_h))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # モーダルウィンドウ（白い背景領域）の精密検出
    hsv_detect = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    white_mask = cv2.inRange(hsv_detect, np.array([0, 0, 200]), np.array([180, 50, 255]))
    kernel = np.ones((10, 10), np.uint8)
    white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
    cnts_white, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    modal_roi = None
    if cnts_white:
        sorted_cnts = sorted(cnts_white, key=cv2.contourArea, reverse=True)
        for cnt in sorted_cnts:
            x, y, w, h = cv2.boundingRect(cnt)
            if w > img.shape[1] * 0.25 and h > img.shape[0] * 0.15:
                modal_roi = (x, y, w, h)
                break
                
    if modal_roi is None:
        modal_roi = (0, 0, img.shape[1], img.shape[0])
        
    mx, my, mw, mh = modal_roi
    modal = img[my:my+mh, mx:mx+mw]

    hsv = cv2.cvtColor(modal, cv2.COLOR_BGR2HSV)

    min_saturation = 50
    lower_cyan = np.array([70, min_saturation, 100])
    upper_cyan = np.array([110, 255, 255])

    lower_red1 = np.array([0, min_saturation, 100])
    upper_red1 = np.array([15, 255, 255])
    lower_red2 = np.array([165, min_saturation, 100])
    upper_red2 = np.array([180, 255, 255])

    cyan_mask = cv2.inRange(hsv, lower_cyan, upper_cyan)
    red_mask = cv2.bitwise_or(
        cv2.inRange(hsv, lower_red1, upper_red1),
        cv2.inRange(hsv, lower_red2, upper_red2)
    )

    # バッジの文字による分断を結合する
    kernel_close = np.ones((5, 5), np.uint8)
    cyan_mask = cv2.morphologyEx(cyan_mask, cv2.MORPH_CLOSE, kernel_close)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel_close)

    def get_blobs(mask, color_type):
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        blobs = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area > 20:  # 小さい破片も拾うようにしきい値を緩和
                x, y = centroids[i]
                if y > mh * 0.25 and x < mw * 0.75:  # モーダル上部のヘッダーや右端のボタン(再生ボタン等)を除外
                    blobs.append({
                        'x': x,
                        'y': y,
                        'area': area,
                        'type': color_type
                    })
        return blobs

    all_blobs = get_blobs(cyan_mask, 'WIN') + get_blobs(red_mask, 'LOSE')
    all_blobs.sort(key=lambda b: b['y'])

    # Y座標が近いブロブをグループ化（15ピクセル以内の差なら同グループ）
    raw_groups = []
    current_group = []
    for b in all_blobs:
        if not current_group:
            current_group.append(b)
        else:
            if abs(b['y'] - current_group[0]['y']) < 15:
                current_group.append(b)
            else:
                raw_groups.append(current_group)
                current_group = [b]
    if current_group:
        raw_groups.append(current_group)

    # 「水色(WIN)と赤色(LOSE)の両方が存在しているグループのみ」をラウンド候補としてフィルタリング
    valid_groups = []
    for g in raw_groups:
        has_win = any(b['type'] == 'WIN' for b in g)
        has_lose = any(b['type'] == 'LOSE' for b in g)
        if has_win and has_lose:
            valid_groups.append(g)

    # 画面下部にある5つの有効グループを5ラウンドとみなす
    if len(valid_groups) >= 5:
        round_groups = valid_groups[-5:]
    else:
        round_groups = []

    rounds = []
    left_wins = 0
    right_wins = 0
    
    # OCRフォールバック用
    badge_half_w = int(mw * 0.15)
    vs_x = int(mw * 0.38) 

    for i in range(5):
        left_res, right_res = None, None
        
        if len(round_groups) == 5:
            group = round_groups[i]
            cyan_xs = [b['x'] for b in group if b['type'] == 'WIN']
            red_xs = [b['x'] for b in group if b['type'] == 'LOSE']
            
            if cyan_xs and red_xs:
                cyan_cx = sum(cyan_xs) / len(cyan_xs)
                red_cx = sum(red_xs) / len(red_xs)
                if cyan_cx < red_cx:
                    left_res, right_res = "WIN", "LOSE"
                else:
                    left_res, right_res = "LOSE", "WIN"
            else:
                # 片方の色しか見つからない場合はOCR
                group_y = sum(b['y'] for b in group) / len(group)
                ry1 = max(0, int(group_y - 40))
                ry2 = min(mh, int(group_y + 40))
                row_bgr = modal[ry1:ry2, :]
                left_x1 = max(vs_x - badge_half_w, 0)
                right_x2 = min(vs_x + badge_half_w, mw)
                left_res, right_res = _ocr_fallback(row_bgr, left_x1, vs_x, vs_x, right_x2)
        else:
            # 万が一5グループ見つからなかった場合の完全フォールバック（旧方式の領域を0.94に拡張）
            start_y = int(mh * 0.38)
            end_y = int(mh * 0.94)  
            row_h = (end_y - start_y) / 5.0
            ry1 = int(start_y + i * row_h)
            ry2 = int(start_y + (i + 1) * row_h)
            row_bgr = modal[ry1:ry2, :]
            
            left_x1 = max(vs_x - badge_half_w, 0)
            right_x2 = min(vs_x + badge_half_w, mw)
            left_res, right_res = _ocr_fallback(row_bgr, left_x1, vs_x, vs_x, right_x2)
            
        if left_res == "WIN":
            left_wins += 1
        if right_res == "WIN":
            right_wins += 1

        rounds.append({
            "round": i + 1,
            "left": left_res,
            "right": right_res
        })

    winner = "left" if left_wins > right_wins else "right"

    return {
        "rounds": rounds,
        "winner": winner
    }

def _ocr_fallback(row_bgr, left_x1, left_x2, right_x1, right_x2):
    left_crop = row_bgr[:, left_x1:left_x2]
    right_crop = row_bgr[:, right_x1:right_x2]

    l_gray = cv2.cvtColor(left_crop, cv2.COLOR_BGR2GRAY)
    r_gray = cv2.cvtColor(right_crop, cv2.COLOR_BGR2GRAY)

    _, l_thresh = cv2.threshold(l_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, r_thresh = cv2.threshold(r_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    l_text = pytesseract.image_to_string(l_thresh, config='--psm 7').strip().upper()
    r_text = pytesseract.image_to_string(r_thresh, config='--psm 7').strip().upper()

    left_res = "WIN"
    right_res = "LOSE"

    if "W" in l_text or "I" in l_text:
        left_res = "WIN"
    elif "L" in l_text or "O" in l_text:
        left_res = "LOSE"

    if "W" in r_text or "I" in r_text:
        right_res = "WIN"
    elif "L" in r_text or "O" in r_text:
        right_res = "LOSE"

    if left_res == right_res:
        left_res, right_res = "LOSE", "WIN"

    return left_res, right_res
