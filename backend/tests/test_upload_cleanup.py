import os
import tempfile
import time
import unittest
from pathlib import Path

from services import upload_cleanup


class UploadCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.cropped = self.root / "cropped"
        self.templates = self.root / "templates"
        self.cropped.mkdir()
        self.templates.mkdir()
        self.original_root = upload_cleanup.UPLOAD_ROOT
        self.original_cropped = upload_cleanup.CROPPED_DIR
        upload_cleanup.UPLOAD_ROOT = self.root
        upload_cleanup.CROPPED_DIR = self.cropped

    def tearDown(self):
        upload_cleanup.UPLOAD_ROOT = self.original_root
        upload_cleanup.CROPPED_DIR = self.original_cropped
        self.temp_dir.cleanup()

    def make_stale(self, path: Path):
        path.write_bytes(b"image")
        old_time = time.time() - 48 * 60 * 60
        os.utime(path, (old_time, old_time))

    def test_stale_cleanup_preserves_templates_and_referenced_icons(self):
        raw = self.root / "tour_1_seed_1_img_0.png"
        match = self.root / "match_t1_a1_d2.png"
        crop = self.cropped / "crop_t1_s1_r1_c1.png"
        unused_icon = self.cropped / "player_icon_unused.png"
        referenced_icon = self.cropped / "player_icon_used.png"
        template = self.templates / "char_1_001.png"
        fresh_crop = self.cropped / "crop_fresh.png"

        for path in (raw, match, crop, unused_icon, referenced_icon, template):
            self.make_stale(path)
        fresh_crop.write_bytes(b"image")

        deleted = upload_cleanup.cleanup_stale_uploads(
            {"/api/uploads/cropped/player_icon_used.png"},
            max_age_hours=24,
        )

        self.assertEqual(deleted, 4)
        self.assertFalse(raw.exists())
        self.assertFalse(match.exists())
        self.assertFalse(crop.exists())
        self.assertFalse(unused_icon.exists())
        self.assertTrue(referenced_icon.exists())
        self.assertTrue(template.exists())
        self.assertTrue(fresh_crop.exists())

    def test_upload_url_rejects_paths_outside_upload_root(self):
        self.assertIsNone(
            upload_cleanup.path_from_upload_url(
                "/api/uploads/../../outside.png"
            )
        )

    def test_registered_crop_cleanup_only_deletes_temporary_crops(self):
        crop = self.cropped / "crop_t1_s1_r1_c1.png"
        icon = self.cropped / "player_icon_used.png"
        crop.write_bytes(b"crop")
        icon.write_bytes(b"icon")

        deleted = upload_cleanup.delete_temporary_crop_urls([
            "/api/uploads/cropped/crop_t1_s1_r1_c1.png",
            "/api/uploads/cropped/player_icon_used.png",
        ])

        self.assertEqual(deleted, 1)
        self.assertFalse(crop.exists())
        self.assertTrue(icon.exists())


if __name__ == "__main__":
    unittest.main()
