import cv2
from services.image_processor import process_images
res=process_images(["/app/empty_test.png"], "test", 1)
print(res)
