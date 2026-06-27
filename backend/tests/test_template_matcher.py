import unittest
import sys
from unittest.mock import MagicMock

import numpy as np

sys.modules.setdefault("cv2", MagicMock())
from services.template_matcher import predict_character
import services.template_matcher as template_matcher


class TemplateMatcherTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.face = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
        template_matcher.cv2.cvtColor.side_effect = lambda image, _mode: image
        template_matcher.cv2.matchTemplate.side_effect = (
            lambda face, template, _method: np.array(
                [[1.0 if np.array_equal(face, template) else 0.2]],
                dtype=np.float32,
            )
        )
        template_matcher.cv2.minMaxLoc.side_effect = (
            lambda result: (
                float(result.min()),
                float(result.max()),
                (0, 0),
                (0, 0),
            )
        )

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


if __name__ == "__main__":
    unittest.main()
