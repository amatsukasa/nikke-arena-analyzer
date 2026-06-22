import cv2
import numpy as np
import sys

def main():
    img_path = sys.argv[1]
    img = cv2.imread(img_path)
    if img is None:
        print("Could not read image")
        return

    h, w, _ = img.shape
    print(f"Image resolution: {w}x{h}")

    # Convert to HSV to find light blue (cyan) color
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Cyan color range in HSV
    lower_cyan = np.array([80, 100, 100])
    upper_cyan = np.array([100, 255, 255])
    
    mask = cv2.inRange(hsv, lower_cyan, upper_cyan)
    
    # Find contours of cyan regions
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    cyan_regions = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 100: # Filter noise
            x, y, w_box, h_box = cv2.boundingRect(cnt)
            cyan_regions.append({"x": x, "y": y, "w": w_box, "h": h_box, "area": area})
    
    # Sort by area descending
    cyan_regions.sort(key=lambda x: x["area"], reverse=True)
    
    print(f"Found {len(cyan_regions)} significant cyan regions.")
    for i, reg in enumerate(cyan_regions[:5]):
        print(f"Region {i+1}: x={reg['x']}, y={reg['y']}, w={reg['w']}, h={reg['h']}, area={reg['area']}")

if __name__ == "__main__":
    main()
