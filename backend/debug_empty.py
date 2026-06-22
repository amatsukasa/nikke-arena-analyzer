import cv2
import numpy as np
import os
from services.image_processor import process_images
from services.template_matcher import get_templates

res = process_images(["/app/empty_test.png"], "test", 1)

print("----- DEBUG OUTPUT -----")
for c_idx, c in enumerate(res["suggested_teams"][0]):
    print(f"Slot {c_idx+1}: predicted_id={c['predicted_character_id']}, conf={c['confidence']}")
