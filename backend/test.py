import cv2
import numpy as np

img = cv2.imread('/app/test_img.png')
print(f"Original shape: {img.shape}")

hsv_detect = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
white_mask = cv2.inRange(hsv_detect,
    np.array([0, 0, 200]),
    np.array([180, 50, 255]))
kernel = np.ones((10, 10), np.uint8)
white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
cnts_white, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

modal_roi = None
if cnts_white:
    sorted_cnts = sorted(cnts_white, key=cv2.contourArea, reverse=True)
    for cnt in sorted_cnts:
        x, y, w, h = cv2.boundingRect(cnt)
        print(f"Found white contour: w={w}, h={h} (w_ratio={w/img.shape[1]:.3f}, h_ratio={h/img.shape[0]:.3f})")
        if w > img.shape[1] * 0.25 and h > img.shape[0] * 0.2:
            modal_roi = (x, y, w, h)
            print(" -> ACCEPTED by new logic (w > 0.25, h > 0.2)")
            break


if modal_roi is None:
    print("Modal ROI not found using current logic!")
