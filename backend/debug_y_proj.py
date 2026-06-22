import cv2
import numpy as np

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

hsv = cv2.cvtColor(modal, cv2.COLOR_BGR2HSV)
min_saturation = 80
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
colored = cv2.bitwise_or(cyan_mask, red_mask)

y_density = np.sum(colored > 0, axis=1).astype(float)
kernel = np.ones(11) / 11
smoothed_y = np.convolve(y_density, kernel, mode='same')

# Find peaks in smoothed_y
peaks = []
for i in range(1, len(smoothed_y) - 1):
    if smoothed_y[i] > smoothed_y[i-1] and smoothed_y[i] > smoothed_y[i+1]:
        if smoothed_y[i] > np.max(smoothed_y) * 0.1:
            peaks.append((i, smoothed_y[i]))

peaks.sort(key=lambda x: x[0])
print(f"Modal height: {mh}")
for p in peaks:
    print(f"Peak at Y={p[0]}, density={p[1]}")
