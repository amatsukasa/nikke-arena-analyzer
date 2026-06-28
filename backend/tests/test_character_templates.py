import tempfile
import unittest
from pathlib import Path

from services.character_templates import find_character_template


class CharacterTemplateTests(unittest.TestCase):
    def test_prefers_legacy_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            template_dir.mkdir()
            legacy = template_dir / "char_10.png"
            legacy.write_bytes(b"legacy")
            (template_dir / "char_10_001.png").write_bytes(b"numbered")

            self.assertEqual(find_character_template(tmp, 10), legacy)

    def test_returns_first_numbered_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            template_dir.mkdir()
            expected = template_dir / "char_20_001.png"
            (template_dir / "char_20_002.png").write_bytes(b"second")
            expected.write_bytes(b"first")

            self.assertEqual(find_character_template(tmp, 20), expected)

    def test_ignores_stale_database_state_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_character_template(tmp, 30))


if __name__ == "__main__":
    unittest.main()
