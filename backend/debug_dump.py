import cv2
import numpy as np
import os

img_path = "/app/test_img.png"
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

os.makedirs("/app/debug_output", exist_ok=True)

for i in range(5):
    ry1 = int(start_y + i * row_h)
    ry2 = int(start_y + (i + 1) * row_h)
    row_bgr = modal[ry1:ry2, :]
    cv2.imwrite(f"/app/debug_output/row_{i+1}.png", row_bgr)

print("Saved cropped rows to /app/debug_output/")
