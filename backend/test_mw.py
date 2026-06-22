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
print("MODAL ROI:", modal_roi)
