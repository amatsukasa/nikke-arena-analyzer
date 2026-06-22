import cv2, numpy as np
from services.image_processor import process_images
import services.template_matcher as tm

# Hook predict_character to print information
orig_predict = tm.predict_character

def mock_predict(face, templates, threshold):
    hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    avg_s = np.mean(hsv[:, :, 1])
    avg_v = np.mean(hsv[:, :, 2])
    print(f"Face shape: {face.shape}, avg_s: {avg_s:.1f}, avg_v: {avg_v:.1f}")
    return orig_predict(face, templates, threshold)

tm.predict_character = mock_predict

res = process_images(['/app/empty_test.png'], "test", 1)
