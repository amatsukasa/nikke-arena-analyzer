import cv2
import os
from services.match_processor import extract_match_results
from services.image_processor import process_images

upload_dir = "/app/uploads"
images = [f for f in os.listdir(upload_dir) if f.startswith("10000038") and f.endswith(".png")]
images.sort()

for img_name in images:
    path = os.path.join(upload_dir, img_name)
    img = cv2.imread(path)
    if img is None:
        continue
    h, w, _ = img.shape
    print(f"\n--- {img_name} (Resolution: {w}x{h}) ---")
    
    # Try match result first
    try:
        res = extract_match_results(path)
        print("DETECTED AS MATCH RESULT:")
        print(res)
        continue
    except Exception as e:
        print(f"Not a match result: {e}")
        
    # Try deck analysis
    try:
        res = process_images([path], 1, 1)
        print("DETECTED AS DECK:")
        print("Player Name:", res.get('suggested_player_name'))
    except Exception as e:
        print(f"Deck processing failed: {e}")
