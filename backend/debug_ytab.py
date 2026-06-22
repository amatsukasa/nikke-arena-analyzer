import glob
import cv2
import numpy as np

files = glob.glob('/app/media__17812630286*.png')
files.sort()

for path in files:
    img = cv2.imread(path)
    if img is None: continue
    
    hsv_detect = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    white_mask = cv2.morphologyEx(cv2.inRange(hsv_detect, np.array([0, 0, 200]), np.array([180, 50, 255])), cv2.MORPH_CLOSE, np.ones((10, 10), np.uint8))
    cnts_white, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    sorted_cnts = sorted(cnts_white, key=cv2.contourArea, reverse=True)
    modal_roi = None
    for cnt in sorted_cnts:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > img.shape[1] * 0.25 and h > img.shape[0] * 0.2:
            modal_roi = (x, y, w, h)
            break
            
    m_x, m_y, m_w, m_h = modal_roi
    img_res = cv2.resize(img[m_y:m_y+m_h, m_x:m_x+m_w], (1080, int(m_h * 1080.0 / m_w)))
    
    hsv = cv2.cvtColor(img_res, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([75, 50, 50]), np.array([105, 255, 255]))
    cnts_cyan, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if cnts_cyan:
        c = max(cnts_cyan, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(c)
        print(f'{path}: x={x}, w={w}, anchor={x + w // 2}')
