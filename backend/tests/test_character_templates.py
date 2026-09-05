import tempfile
import unittest
from pathlib import Path

from services.character_templates import find_character_template, get_character_template_inventory


class CharacterTemplateTests(unittest.TestCase):
    def test_prefers_latest_active_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            template_dir.mkdir()
            legacy = template_dir / "char_10.png"
            legacy.write_bytes(b"legacy")
            (template_dir / "char_10_001.png").write_bytes(b"numbered")

            self.assertEqual(find_character_template(tmp, 10), template_dir / "char_10_001.png")

    def test_returns_latest_numbered_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            template_dir.mkdir()
            expected = template_dir / "char_20_002.png"
            expected.write_bytes(b"second")
            (template_dir / "char_20_001.png").write_bytes(b"first")

            self.assertEqual(find_character_template(tmp, 20), expected)

    def test_ignores_stale_database_state_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_character_template(tmp, 30))

    def test_inventory_reports_legacy_and_numbered_templates_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            template_dir.mkdir()
            legacy = template_dir / "char_10.png"
            legacy.write_bytes(b"legacy")
            (template_dir / "char_10_002.png").write_bytes(b"numbered")
            numbered = template_dir / "char_20_001.png"
            numbered.write_bytes(b"numbered")
            (template_dir / "not_a_template.png").write_bytes(b"ignored")

            self.assertEqual(
                get_character_template_inventory(tmp),
                {10: template_dir / "char_10_002.png", 20: numbered},
            )


if __name__ == "__main__":
    unittest.main()
