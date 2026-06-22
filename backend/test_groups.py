import cv2, numpy as np
img=cv2.imread('/app/uploads/match_t14_a13_d58.png')
orig_h, orig_w = img.shape[:2]
target_w = 1080
target_h = int(orig_h * target_w / orig_w)
img = cv2.resize(img, (target_w, target_h))
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
        if w > img.shape[1] * 0.25 and h > img.shape[0] * 0.2:
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
kernel_close = np.ones((5, 5), np.uint8)
cyan_mask = cv2.morphologyEx(cyan_mask, cv2.MORPH_CLOSE, kernel_close)
red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel_close)

def get_blobs(mask, color_type):
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    blobs = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > 20:
            x, y = centroids[i]
            if y > mh * 0.25:
                blobs.append({'x': x, 'y': y, 'area': area, 'type': color_type})
    return blobs
all_blobs = get_blobs(cyan_mask, 'WIN') + get_blobs(red_mask, 'LOSE')
all_blobs.sort(key=lambda b: b['y'])
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
valid_groups = []
for g in raw_groups:
    has_win = any(b['type'] == 'WIN' for b in g)
    has_lose = any(b['type'] == 'LOSE' for b in g)
    if has_win and has_lose:
        valid_groups.append(g)

print("VALID GROUPS:", len(valid_groups))
for g in valid_groups:
    print(g)
