import json
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import collection_classifier


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "collection"


def _bgr_from_hsv(hue: int, saturation: int, value: int) -> tuple[int, int, int]:
    hsv = np.array([[[hue, saturation, value]]], dtype=np.uint8)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
    return tuple(int(channel) for channel in bgr)


def _synthetic_badge(
    hue: int,
    *,
    level_15: bool,
) -> np.ndarray:
    face = np.full((160, 160, 3), 220, dtype=np.uint8)
    outer_color = _bgr_from_hsv(hue, 220, 190)
    polygon = np.array(
        [[2, 72], [7, 66], [24, 66], [30, 72], [24, 80], [7, 80]],
        dtype=np.int32,
    )
    cv2.fillConvexPoly(face, polygon, outer_color)
    inner_value = 35 if level_15 else 180
    inner_color = _bgr_from_hsv(hue, 180, inner_value)
    cv2.rectangle(face, (8, 69), (23, 77), inner_color, -1)
    return face


class CollectionClassifierTests(unittest.TestCase):
    def test_classifies_all_rarities_and_level_bands(self):
        cases = [
            (90, False, "r_0_14"),
            (90, True, "r_15"),
            (145, False, "sr_0_14"),
            (145, True, "sr_15"),
            (15, False, "treasure_0_14"),
            (15, True, "treasure_15"),
        ]
        for hue, level_15, expected in cases:
            with self.subTest(expected=expected):
                result, confidence = collection_classifier.classify_collection(
                    _synthetic_badge(hue, level_15=level_15)
                )
                self.assertEqual(result, expected)
                self.assertGreaterEqual(confidence, 0.7)

    def test_character_color_without_badge_shape_is_none(self):
        face = np.zeros((160, 160, 3), dtype=np.uint8)
        orange = _bgr_from_hsv(15, 220, 190)
        # Reproduces the old false positive: a tall strip of character artwork.
        face[55:105, 0:32] = orange
        result = collection_classifier.analyze_collection(face)
        self.assertFalse(result["has_collection"])
        self.assertIsNone(result["rarity"])
        self.assertEqual(result["debug_info"]["reason"], "no_badge_shaped_component")

    def test_real_regression_fixtures(self):
        expected = json.loads(
            (FIXTURE_DIR / "expected.json").read_text(encoding="utf-8")
        )
        for filename, values in expected.items():
            with self.subTest(filename=filename):
                face = cv2.imread(str(FIXTURE_DIR / filename))
                self.assertIsNotNone(face)
                result = collection_classifier.analyze_collection(face)
                self.assertEqual(result["has_collection"], values["has_collection"])
                self.assertEqual(result["rarity"], values["rarity"])
                self.assertEqual(result["level"], values["level"])
                self.assertGreaterEqual(result["confidence"], values["min_confidence"])

    def test_empty_input_is_safe(self):
        result = collection_classifier.analyze_collection(
            np.empty((0, 0, 3), dtype=np.uint8)
        )
        self.assertFalse(result["has_collection"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(
            collection_classifier.classify_collection(
                np.empty((0, 0, 3), dtype=np.uint8)
            ),
            ("none", 0.0),
        )

    def test_debug_images_are_written(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            collection_classifier.analyze_collection(
                _synthetic_badge(145, level_15=True),
                debug=True,
                debug_dir=temp_dir,
                debug_prefix="sample",
            )
            names = {path.name for path in Path(temp_dir).iterdir()}
            self.assertTrue(
                {
                    "sample_normalized.png",
                    "sample_roi.png",
                    "sample_mask_r.png",
                    "sample_mask_sr.png",
                    "sample_mask_treasure.png",
                    "sample_detected.png",
                }.issubset(names)
            )

    def test_masks_collection_region_without_mutating_source(self):
        image = np.zeros((160, 160, 3), dtype=np.uint8)
        masked = collection_classifier.mask_collection_icon(image)
        self.assertTrue(np.all(masked[50:110, 0:36] == 127))
        self.assertTrue(np.all(masked[:, 36:] == 0))
        self.assertTrue(np.all(image == 0))


if __name__ == "__main__":
    unittest.main()
