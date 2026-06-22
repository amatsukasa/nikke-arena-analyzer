import cv2
import numpy as np
import sys

def test_extract(image_path):
    print(f"Testing {image_path}")
    img = cv2.imread(image_path)
    if img is None:
        print("Failed to load image")
        return
        
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
            print(f"Contour: x={x}, y={y}, w={w}, h={h}, area={w*h}")
            if w > img.shape[1] * 0.3 and h > img.shape[0] * 0.2:
                modal_roi = (x, y, w, h)
                print(f"Selected modal ROI: {modal_roi}")
                break
                
    if modal_roi is None:
        print("Fallback: Using full image")
        modal_roi = (0, 0, img.shape[1], img.shape[0])
        
    m_x, m_y, m_w, m_h = modal_roi
    img_modal = img[m_y:m_y+m_h, m_x:m_x+m_w]
    
    scale = 1080.0 / m_w
    img_res = cv2.resize(img_modal, (1080, int(m_h * scale)))
    
    print(f"Resized modal shape: {img_res.shape}")
    
    lower_cyan = np.array([75, 50, 50])
    upper_cyan = np.array([105, 255, 255])
    hsv = cv2.cvtColor(img_res, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_cyan, upper_cyan)
    cnts_cyan, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if cnts_cyan:
        c = max(cnts_cyan, key=cv2.contourArea)
        x_tab, y_tab, w_tab, h_tab = cv2.boundingRect(c)
        print(f"Cyan tab: x={x_tab}, y={y_tab}, w={w_tab}, h={h_tab}")
    else:
        print("Cyan tab not found")

if __name__ == '__main__':
    test_extract(sys.argv[1])
