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


def _synthetic_compact_badge(hue: int, *, x_offset: int = 0) -> np.ndarray:
    """Reproduce the small 0-14 centre jewel seen after browser resizing."""
    face = np.full((160, 160, 3), 220, dtype=np.uint8)
    color = _bgr_from_hsv(hue, 220, 190)
    polygon = np.array(
        [
            [8 + x_offset, 76],
            [11 + x_offset, 72],
            [18 + x_offset, 72],
            [22 + x_offset, 76],
            [18 + x_offset, 80],
            [11 + x_offset, 80],
        ],
        dtype=np.int32,
    )
    cv2.fillConvexPoly(face, polygon, color)
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

    def test_recovers_treasure_badge_merged_with_character_art(self):
        face = np.full((160, 160, 3), 220, dtype=np.uint8)
        orange = _bgr_from_hsv(15, 220, 190)
        badge = collection_classifier._hexagon_points(12, 80, 28, 32)
        cv2.fillConvexPoly(face, badge, orange)
        # Connect the badge to a large artwork-colored region so the normal
        # contour is deliberately too large for the standard shape profile.
        face[75:86, 24:90] = orange
        result = collection_classifier.analyze_collection(face)
        self.assertTrue(result["has_collection"])
        self.assertEqual(result["rarity"], "treasure")
        self.assertEqual(
            result["debug_info"]["candidates"][0]["shape_profile"],
            "hexagon_probe",
        )

    def test_compact_sr_badge_is_not_treated_as_absent(self):
        result = collection_classifier.analyze_collection(
            _synthetic_compact_badge(145)
        )
        self.assertTrue(result["has_collection"])
        self.assertEqual(result["rarity"], "sr")
        self.assertIsNone(result["level"])
        self.assertEqual(result["debug_info"]["level_band"], "0_14")
        self.assertEqual(
            result["debug_info"]["candidates"][0]["shape_profile"],
            "compact",
        )

    def test_left_shifted_compact_sr_badge_is_detected(self):
        result = collection_classifier.analyze_collection(
            _synthetic_compact_badge(145, x_offset=-4)
        )
        self.assertTrue(result["has_collection"])
        self.assertEqual(result["rarity"], "sr")
        self.assertEqual(result["debug_info"]["level_band"], "0_14")

    def test_dark_compact_component_is_level_15(self):
        face = _synthetic_compact_badge(145)
        dark_background = _bgr_from_hsv(145, 40, 35)
        dark_hexagon = collection_classifier._hexagon_points(15, 76, 18, 12)
        cv2.fillConvexPoly(face, dark_hexagon, dark_background)
        colored_pixels = np.any(_synthetic_compact_badge(145) != 220, axis=2)
        face[colored_pixels] = _bgr_from_hsv(145, 180, 35)
        result = collection_classifier.analyze_collection(face)
        self.assertTrue(result["has_collection"])
        self.assertEqual(result["debug_info"]["level_band"], "15")

    def test_returns_hexagon_geometry_for_detected_badge(self):
        result = collection_classifier.analyze_collection(
            _synthetic_badge(145, level_15=True)
        )
        geometry = result["debug_info"]["badge_geometry"]
        self.assertEqual(len(geometry["polygon"]), 6)
        self.assertEqual(len(geometry["inner_polygon"]), 6)
        self.assertGreaterEqual(geometry["hexagon_score"], 0.7)

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
