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
    _extract_modal_roi,
    _write_preview_image,
    write_lossless_png,
)


class ImageProcessorModalTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
