import cv2
import numpy as np
import sys
import os

img_path = "/app/test_img.png"
if not os.path.exists(img_path):
    print("Image not found")
    sys.exit(1)

img = cv2.imread(img_path)
orig_h, orig_w = img.shape[:2]
target_w = 1080
target_h = int(orig_h * target_w / orig_w)
img = cv2.resize(img, (target_w, target_h))

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

largest = max(contours, key=cv2.contourArea)
mx, my, mw, mh = cv2.boundingRect(largest)

modal = img[my:my+mh, mx:mx+mw]

start_y = int(mh * 0.38)
end_y = int(mh * 0.88)
row_h = (end_y - start_y) / 5.0

hsv = cv2.cvtColor(modal, cv2.COLOR_BGR2HSV)
min_saturation = 80
lower_cyan = np.array([70, min_saturation, 100])
upper_cyan = np.array([110, 255, 255])
lower_red1 = np.array([0, min_saturation, 100])
upper_red1 = np.array([15, 255, 255])
lower_red2 = np.array([165, min_saturation, 100])
upper_red2 = np.array([180, 255, 255])

all_colored = np.zeros(mw, dtype=float)
for i in range(5):
    ry1 = int(start_y + i * row_h)
    ry2 = int(start_y + (i + 1) * row_h)
    row_hsv = hsv[ry1:ry2, :]

    cyan_mask = cv2.inRange(row_hsv, lower_cyan, upper_cyan)
    red_mask = cv2.bitwise_or(
        cv2.inRange(row_hsv, lower_red1, upper_red1),
        cv2.inRange(row_hsv, lower_red2, upper_red2)
    )
    colored = cv2.bitwise_or(cyan_mask, red_mask)
    all_colored += np.sum(colored > 0, axis=0).astype(float)

kernel = np.ones(21) / 21
smoothed = np.convolve(all_colored, kernel, mode='same')
peak_val = np.max(smoothed)
threshold = peak_val * 0.10 if peak_val > 0 else 1
above_threshold = np.where(smoothed > threshold)[0]

if len(above_threshold) >= 2:
    color_start = above_threshold[0]
    color_end = above_threshold[-1]
    search_margin = int((color_end - color_start) * 0.2)
    search_start = color_start + search_margin
    search_end = color_end - search_margin
    if search_start < search_end:
        search_region = smoothed[search_start:search_end]
        vs_x = search_start + int(np.argmin(search_region))
    else:
        vs_x = int(mw * 0.38)
else:
    vs_x = int(mw * 0.38)

badge_half_w = int(mw * 0.15)
print(f"vs_x: {vs_x}, badge_half_w: {badge_half_w}")

for i in range(5):
    ry1 = int(start_y + i * row_h)
    ry2 = int(start_y + (i + 1) * row_h)
    row_hsv = hsv[ry1:ry2, :]

    full_cyan_mask = cv2.inRange(row_hsv, lower_cyan, upper_cyan)
    full_red_mask = cv2.bitwise_or(
        cv2.inRange(row_hsv, lower_red1, upper_red1),
        cv2.inRange(row_hsv, lower_red2, upper_red2)
    )

    total_cyan = cv2.countNonZero(full_cyan_mask)
    total_red = cv2.countNonZero(full_red_mask)

    cyan_cx = float(np.mean(np.where(full_cyan_mask > 0)[1])) if total_cyan > 0 else None
    red_cx = float(np.mean(np.where(full_red_mask > 0)[1])) if total_red > 0 else None

    print(f"Round {i+1}: cyan_cx={cyan_cx}, red_cx={red_cx}, total_cyan={total_cyan}, total_red={total_red}")
    if cyan_cx is not None and red_cx is not None:
        margin = abs(cyan_cx - red_cx)
        print(f"  margin: {margin}")
        left_x1 = max(vs_x - badge_half_w, 0)
        right_x2 = min(vs_x + badge_half_w, mw)
        left_cyan = cv2.countNonZero(full_cyan_mask[:, left_x1:vs_x])
        left_red = cv2.countNonZero(full_red_mask[:, left_x1:vs_x])
        right_cyan = cv2.countNonZero(full_cyan_mask[:, vs_x:right_x2])
        right_red = cv2.countNonZero(full_red_mask[:, vs_x:right_x2])
        print(f"  left_cyan={left_cyan}, left_red={left_red}, right_cyan={right_cyan}, right_red={right_red}")
