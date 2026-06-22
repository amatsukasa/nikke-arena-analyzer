import cv2
from services.image_processor import process_images
import services.template_matcher as tm

orig_predict = tm.predict_character
i=0
def mock_predict(face, templates, threshold):
    global i
    cv2.imwrite(f"/app/empty_face_{i}.png", face)
    i+=1
    return orig_predict(face, templates, threshold)
tm.predict_character = mock_predict
process_images(["/app/empty_test.png"], "test", 1)
