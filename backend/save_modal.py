import cv2, numpy as np
img=cv2.imread('/app/uploads/match_t14_a1_d2.png')
orig_h, orig_w = img.shape[:2]
target_w = 1080
target_h = int(orig_h * target_w / orig_w)
img = cv2.resize(img, (target_w, target_h))
modal = img[172:172+307, 390:390+302]
cv2.imwrite('/app/modal_debug.png', modal)
