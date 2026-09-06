import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import cv2

import numpy as np

from services.collection_classifier import collection_match_mask
from services.template_matcher import masked_ccoef_normed, predict_character, prepare_character_image
import services.template_matcher as template_matcher


class TemplateMatcherTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.face = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
        self.cvt_color = patch.object(
            template_matcher.cv2,
            "cvtColor",
            side_effect=lambda image, _mode: image,
        )
        self.match_template = patch.object(
            template_matcher.cv2,
            "matchTemplate",
            side_effect=(
            lambda face, template, _method, **_kwargs: np.array(
                [[1.0 if np.array_equal(face, template) else 0.2]],
                dtype=np.float32,
            )
            ),
        )
        self.min_max_loc = patch.object(
            template_matcher.cv2,
            "minMaxLoc",
            side_effect=(
            lambda result: (
                float(result.min()),
                float(result.max()),
                (0, 0),
                (0, 0),
            )
            ),
        )
        self.cvt_color.start()
        self.match_template.start()
        self.min_max_loc.start()
        self.addCleanup(self.cvt_color.stop)
        self.addCleanup(self.match_template.stop)
        self.addCleanup(self.min_max_loc.stop)

    def test_returns_clear_best_match(self):
        other = np.flip(self.face, axis=1).copy()

        character_id, confidence = predict_character(
            self.face,
            {10: [self.face.copy()], 20: [other]},
        )

        self.assertEqual(character_id, 10)
        self.assertGreaterEqual(confidence, 0.99)

    def test_rejects_ambiguous_match_between_characters(self):
        character_id, confidence = predict_character(
            self.face,
            {10: [self.face.copy()], 20: [self.face.copy()]},
        )

        self.assertIsNone(character_id)
        self.assertGreaterEqual(confidence, 0.99)

    def test_matching_supplies_a_mask_that_excludes_collection_region(self):
        without_collection = np.zeros((160, 160, 3), dtype=np.uint8)
        with_collection = without_collection.copy()
        mask = collection_match_mask(with_collection.shape)
        with_collection[mask == 0] = 255
        expected = collection_match_mask(mask.shape)
        self.assertTrue(np.array_equal(mask, expected))
        self.assertTrue(np.any(mask == 0))
        self.assertTrue(np.any(mask == 255))
        self.assertEqual(masked_ccoef_normed(with_collection, without_collection, mask), 1.0)

    def test_template_decode_is_cached_until_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "char_10_001.png"
            cv2.imwrite(str(path), self.face)
            template_matcher.invalidate_template_cache()
            with patch.object(template_matcher, "TEMPLATE_DIR", directory), patch.object(
                template_matcher.cv2, "imread", wraps=cv2.imread
            ) as imread:
                template_matcher.get_templates()
                template_matcher.get_templates()
                self.assertEqual(imread.call_count, 1)
                path.write_bytes(path.read_bytes() + b"x")
                template_matcher.get_templates()
                self.assertEqual(imread.call_count, 2)

    def test_template_cache_honors_configured_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            for character_id in range(1, 6):
                candidate_image = np.random.default_rng(character_id).integers(
                    0, 256, size=self.face.shape, dtype=np.uint8
                )
                cv2.imwrite(
                    str(Path(directory) / f"char_{character_id}_001.png"),
                    candidate_image,
                )
            template_matcher.invalidate_template_cache()
            with patch.object(template_matcher, "TEMPLATE_DIR", directory), patch.object(
                template_matcher, "TEMPLATE_CACHE_LIMIT", 3
            ):
                templates = template_matcher.get_templates()
            self.assertEqual(sum(len(rows) for rows in templates.values()), 5)
            self.assertEqual(template_matcher.template_cache_size(), 3)

    def test_template_cache_honors_byte_limit_and_evicted_templates_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            for character_id in range(1, 6):
                cv2.imwrite(
                    str(Path(directory) / f"char_{character_id}_001.png"),
                    self.face,
                )
            template_matcher.invalidate_template_cache()
            one_candidate_bytes = self.face.nbytes + self.face[:, :, 0].nbytes
            with patch.object(template_matcher, "TEMPLATE_DIR", directory), patch.object(
                template_matcher, "TEMPLATE_CACHE_MAX_BYTES", one_candidate_bytes * 2
            ), patch.object(template_matcher, "TEMPLATE_CACHE_LIMIT", 2048), patch.object(
                template_matcher.cv2, "imread", wraps=cv2.imread
            ) as imread:
                first = template_matcher.get_templates()
                first_ids = sorted(first)
                first_match = predict_character(
                    first[1][0].image, first, threshold=-1.0, min_margin=-1.0
                )[0]
                first_reads = imread.call_count
                second = template_matcher.get_templates()
                second_match = predict_character(
                    second[1][0].image, second, threshold=-1.0, min_margin=-1.0
                )[0]

            self.assertEqual(first_ids, sorted(second))
            self.assertIsNotNone(first_match)
            self.assertEqual(second_match, first_match)
            self.assertEqual(first_reads, 5)
            self.assertGreater(imread.call_count, first_reads)
            self.assertLessEqual(
                template_matcher.template_cache_nbytes(), one_candidate_bytes * 2
            )


if __name__ == "__main__":
    unittest.main()
