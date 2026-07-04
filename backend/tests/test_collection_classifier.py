import unittest
from unittest.mock import MagicMock
import sys

import numpy as np

fake_cv2 = MagicMock()
fake_cv2.COLOR_BGR2HSV = 40
fake_cv2.resize.side_effect = lambda image, size: image
sys.modules.setdefault("cv2", fake_cv2)

from services import collection_classifier


class CollectionClassifierTests(unittest.TestCase):
    def setUp(self):
        fake_cv2.cvtColor.side_effect = None

    @staticmethod
    def classify_hsv(hue: int, saturation: int, value: int) -> tuple[str, float]:
        hsv = np.zeros((41, 20, 3), dtype=np.uint8)
        hsv[:, :, 0] = hue
        hsv[:, :, 1] = saturation
        hsv[:, :, 2] = value
        fake_cv2.cvtColor.return_value = hsv
        face = np.zeros((160, 160, 3), dtype=np.uint8)
        return collection_classifier.classify_collection(face)

    def test_classifies_all_collection_grades_and_bands(self):
        cases = [
            (90, 200, 220, "r_0_14"),
            (90, 200, 50, "r_15"),
            (145, 200, 220, "sr_0_14"),
            (145, 200, 50, "sr_15"),
            (15, 200, 220, "treasure_0_14"),
            (15, 200, 50, "treasure_15"),
        ]
        for hue, saturation, value, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    self.classify_hsv(hue, saturation, value)[0],
                    expected,
                )

    def test_classifies_missing_icon_as_none(self):
        self.assertEqual(self.classify_hsv(0, 0, 220)[0], "none")

    def test_empty_input_is_unknown(self):
        result = collection_classifier.classify_collection(
            np.empty((0, 0, 3), dtype=np.uint8)
        )
        self.assertEqual(result, ("unknown", 0.0))

    def test_masks_collection_region_without_mutating_source(self):
        image = np.zeros((160, 160, 3), dtype=np.uint8)
        masked = collection_classifier.mask_collection_icon(image)
        self.assertTrue(np.all(masked[50:110, 0:36] == 127))
        self.assertTrue(np.all(masked[:, 36:] == 0))
        self.assertTrue(np.all(image == 0))


if __name__ == "__main__":
    unittest.main()
