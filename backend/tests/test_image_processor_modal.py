import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

import cv2
import numpy as np


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
sys.modules.setdefault("pytesseract", MagicMock())

from services.image_processor import (
    CHARACTER_CROP_CENTERS,
    CHARACTER_CROP_X_OFFSETS,
    _character_crop_left,
    NORMALIZED_MODAL_WIDTH,
    _aligned_character_centers,
    _extract_modal_roi,
    _find_character_card_centers,
    _find_round_tab_anchor,
    _is_alignment_anchor_reliable,
    _resolve_round_character_centers,
    _write_preview_image,
    write_lossless_png,
)


class ImageProcessorModalTests(unittest.TestCase):
    def test_character_crop_offsets_apply_to_every_shared_mode_slot(self):
        self.assertEqual(CHARACTER_CROP_X_OFFSETS, (-7, -6, -5, -2, -2))
        self.assertEqual(
            tuple(
                _character_crop_left(center, index)
                for index, center in enumerate((154, 348, 542, 736, 931))
            ),
            (67, 262, 457, 654, 849),
        )

    def test_pre_cropped_image_skips_modal_detection(self):
        image = np.zeros((278, 538, 3), dtype=np.uint8)
        image[40:220, 100:420] = 255

        self.assertEqual(
            _extract_modal_roi(image, pre_cropped=True),
            (0, 0, 538, 278),
        )

    def test_uncropped_image_keeps_existing_white_panel_detection(self):
        image = np.zeros((400, 600, 3), dtype=np.uint8)
        image[100:300, 150:450] = 255

        x, y, width, height = _extract_modal_roi(
            image,
            pre_cropped=False,
        )

        self.assertLessEqual(abs(x - 150), 2)
        self.assertLessEqual(abs(y - 100), 2)
        self.assertLessEqual(abs((x + width) - 450), 2)
        self.assertLessEqual(abs((y + height) - 300), 2)

    def test_preview_is_small_and_template_png_remains_lossless(self):
        rng = np.random.default_rng(42)
        image = rng.integers(0, 256, size=(160, 160, 3), dtype=np.uint8)

        with tempfile.TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.webp"
            template_path = Path(temp_dir) / "template.png"

            self.assertTrue(_write_preview_image(preview_path, image))
            self.assertTrue(write_lossless_png(template_path, image))

            preview = cv2.imread(str(preview_path))
            template = cv2.imread(str(template_path))
            self.assertEqual(preview.shape, image.shape)
            self.assertTrue(np.array_equal(template, image))
            self.assertLess(preview_path.stat().st_size, template_path.stat().st_size)

    def test_reliable_round_tab_translates_all_character_centers_equally(self):
        for reference in CHARACTER_CROP_CENTERS:
            with self.subTest(reference=reference):
                centers, shift = _aligned_character_centers(reference + 7, True)
                self.assertEqual(shift, 7)
                self.assertEqual(
                    centers,
                    tuple(center + 7 for center in CHARACTER_CROP_CENTERS),
                )
                self.assertEqual(list(centers), sorted(centers))

    def test_unreliable_or_excessive_alignment_uses_existing_fixed_centers(self):
        for anchor, reliable in ((560, False), (565, True), (515, True)):
            with self.subTest(anchor=anchor, reliable=reliable):
                centers, shift = _aligned_character_centers(anchor, reliable)
                self.assertEqual(centers, CHARACTER_CROP_CENTERS)
                self.assertEqual(shift, 0)

    def test_maximum_alignment_shift_keeps_every_crop_inside_normalized_image(self):
        for shift in (-24, 24):
            centers, applied = _aligned_character_centers(540 + shift, True)
            self.assertEqual(applied, shift)
            for center in centers:
                self.assertGreaterEqual(center - 80, 0)
                self.assertLessEqual(center + 80, NORMALIZED_MODAL_WIDTH)

    def test_alignment_requires_a_tab_sized_dense_cyan_component(self):
        self.assertTrue(_is_alignment_anchor_reliable(183, 77, 10_000, 558))
        self.assertFalse(_is_alignment_anchor_reliable(30, 20, 500, 558))
        self.assertFalse(_is_alignment_anchor_reliable(183, 77, 100, 558))
        self.assertFalse(_is_alignment_anchor_reliable(400, 77, 20_000, 558))

    def test_round_tab_anchor_survives_resize_jpeg_and_surrounding_shadow(self):
        for source_width, jpeg_quality, shift in (
            (1080, 95, -8),
            (720, 55, 6),
            (1440, 35, 12),
        ):
            with self.subTest(
                source_width=source_width,
                jpeg_quality=jpeg_quality,
                shift=shift,
            ):
                source_height = round(558 * source_width / 1080)
                image = np.full((source_height, source_width, 3), 238, dtype=np.uint8)
                scale = source_width / 1080
                x1 = round((449 + shift) * scale)
                x2 = round((633 + shift) * scale)
                y1, y2 = round(29 * scale), round(106 * scale)
                cv2.rectangle(image, (x1 - 5, y1 - 5), (x2 + 5, y2 + 5), (40, 40, 40), -1)
                cv2.rectangle(image, (x1, y1), (x2, y2), (235, 175, 20), -1)
                encoded_ok, encoded = cv2.imencode(
                    ".jpg",
                    image,
                    [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
                )
                self.assertTrue(encoded_ok)
                decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                normalized = cv2.resize(decoded, (1080, 558))

                _, anchor, reliable = _find_round_tab_anchor(normalized)
                centers, applied = _aligned_character_centers(anchor, reliable)

                self.assertTrue(reliable)
                self.assertLessEqual(abs(anchor - (541 + shift)), 2)
                self.assertLessEqual(abs(applied - shift), 2)
                self.assertEqual(list(centers), sorted(centers))

    def test_missing_round_tab_keeps_existing_anchor_and_centers(self):
        image = np.full((558, 1080, 3), 238, dtype=np.uint8)
        y, anchor, reliable = _find_round_tab_anchor(image)
        centers, shift = _aligned_character_centers(anchor, reliable)

        self.assertEqual((y, anchor, reliable), (400, 540, False))
        self.assertEqual(centers, CHARACTER_CROP_CENTERS)
        self.assertEqual(shift, 0)

    def test_round_tab_bounds_produce_individual_character_centers(self):
        image = np.full((558, 1080, 3), 90, dtype=np.uint8)
        expected_pairs = (
            (56, 240),
            (253, 437),
            (456, 633),
            (653, 829),
            (850, 1026),
        )
        for left, right in expected_pairs:
            cv2.rectangle(image, (left, 30), (right, 104), (235, 235, 235), -1)

        centers, reliable = _find_character_card_centers(
            image,
            0,
            CHARACTER_CROP_CENTERS,
        )

        self.assertTrue(reliable)
        self.assertTrue(
            all(abs(actual - wanted) <= 1 for actual, wanted in zip(
                centers,
                (148, 345, 544, 741, 938),
            ))
        )

    def test_round_tab_detection_tracks_global_shift_after_jpeg_compression(self):
        for shift in (-8, 7, 12):
            with self.subTest(shift=shift):
                image = np.full((558, 1080, 3), 90, dtype=np.uint8)
                for left, right in (
                    (56, 240),
                    (253, 437),
                    (456, 633),
                    (653, 829),
                    (850, 1026),
                ):
                    cv2.rectangle(
                        image,
                        (left + shift, 30),
                        (right + shift, 104),
                        (235, 235, 235),
                        -1,
                    )
                ok, encoded = cv2.imencode(
                    ".jpg",
                    image,
                    [cv2.IMWRITE_JPEG_QUALITY, 40],
                )
                self.assertTrue(ok)

                centers, reliable = _find_character_card_centers(
                    cv2.imdecode(encoded, cv2.IMREAD_COLOR),
                    shift,
                    tuple(center + shift for center in CHARACTER_CROP_CENTERS),
                )

                self.assertTrue(reliable)
                expected = tuple(
                    center + shift for center in (148, 345, 544, 741, 938)
                )
                self.assertTrue(
                    all(abs(actual - wanted) <= 2 for actual, wanted in zip(centers, expected))
                )

    def test_unclear_round_tab_grid_preserves_aligned_fallback_centers(self):
        image = np.full((558, 1080, 3), 180, dtype=np.uint8)
        fallback = tuple(center + 6 for center in CHARACTER_CROP_CENTERS)

        centers, reliable = _find_character_card_centers(image, 6, fallback)

        self.assertFalse(reliable)
        self.assertEqual(centers, fallback)

    def test_round_one_tab_grid_is_reused_for_all_round_images(self):
        round_one = np.full((558, 1080, 3), 90, dtype=np.uint8)
        for left, right in (
            (56, 240),
            (253, 437),
            (456, 633),
            (653, 829),
            (850, 1026),
        ):
            cv2.rectangle(round_one, (left, 30), (right, 104), (235, 235, 235), -1)
        other_round = np.full((558, 1080, 3), 180, dtype=np.uint8)
        rounds_data = [
            {
                "img": round_one,
                "x_anchor": 152,
                "alignment_anchor_is_reliable": True,
            },
            {
                "img": other_round,
                "x_anchor": 347,
                "alignment_anchor_is_reliable": True,
            },
        ]

        centers_by_round = _resolve_round_character_centers(rounds_data)

        self.assertEqual(len(centers_by_round), 2)
        self.assertTrue(
            all(abs(actual - wanted) <= 1 for actual, wanted in zip(
                centers_by_round[0],
                (148, 345, 544, 741, 938),
            ))
        )
        self.assertEqual(centers_by_round[1], centers_by_round[0])


if __name__ == "__main__":
    unittest.main()
