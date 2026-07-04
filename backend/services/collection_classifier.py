import cv2
import numpy as np


COLLECTION_VALUES = {
    "none",
    "r_0_14",
    "r_15",
    "sr_0_14",
    "sr_15",
    "treasure_0_14",
    "treasure_15",
    "unknown",
}


def _normalized_face(face: np.ndarray) -> np.ndarray:
    if face.shape[:2] == (160, 160):
        return face
    return cv2.resize(face, (160, 160))


def classify_collection(face: np.ndarray) -> tuple[str, float]:
    if face is None or face.size == 0:
        return "unknown", 0.0

    normalized = _normalized_face(face)
    roi = normalized[55:96, 0:20]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    # Level 15 icons are intentionally dark, so brightness cannot be part of
    # the color-presence mask. Saturation and hue identify the grade.
    colored = saturation > 110

    color_counts = {
        "r": int(np.sum(colored & (hue >= 80) & (hue <= 105))),
        "sr": int(np.sum(colored & (hue >= 125) & (hue <= 165))),
        "treasure": int(np.sum(colored & (hue >= 3) & (hue <= 25))),
    }
    ranked_colors = sorted(color_counts.items(), key=lambda item: item[1], reverse=True)
    grade, best_count = ranked_colors[0]
    second_count = ranked_colors[1][1]

    if best_count < 50:
        return "none", min(1.0, (50 - best_count) / 50)
    if best_count - second_count < 35:
        return "unknown", 0.0

    dark_count = int(np.sum(value < 85))
    level_band = "15" if dark_count > 200 else "0_14"
    color_confidence = min(1.0, (best_count - second_count) / 100)
    level_confidence = min(1.0, abs(dark_count - 200) / 180)
    return f"{grade}_{level_band}", round(min(color_confidence, level_confidence), 3)


def mask_collection_icon(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    masked = image.copy()
    height, width = masked.shape[:2]
    x_end = max(1, round(width * 36 / 160))
    y_start = max(0, round(height * 50 / 160))
    y_end = min(height, round(height * 110 / 160))
    masked[y_start:y_end, 0:x_end] = 127
    return masked
