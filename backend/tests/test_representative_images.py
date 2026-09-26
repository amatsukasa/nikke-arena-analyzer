import os
from pathlib import Path
import sys
import tempfile
import unittest


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import Base, SessionLocal, engine  # noqa: E402
import models  # noqa: E402
from services.representative_images import initialize_representative_templates  # noqa: E402


class RepresentativeImageInitializationTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.temp = tempfile.TemporaryDirectory()
        self.templates = Path(self.temp.name) / "templates"
        self.templates.mkdir()
        self.db.add_all([
            models.Character(id=1, name="A", rarity="SSR"),
            models.Character(id=2, name="B", rarity="SSR"),
            models.Character(id=3, name="C", rarity="SSR"),
            models.Character(
                id=4,
                name="D",
                rarity="SSR",
                representative_template_filename="char_4_009.png",
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_selects_minimum_generation_and_is_idempotent(self):
        for filename in ("char_1_003.png", "char_1_001.png", "char_2.png", "char_4_001.png"):
            (self.templates / filename).write_bytes(filename.encode())

        dry_run = initialize_representative_templates(self.db, self.temp.name)
        self.assertFalse(dry_run["apply"])
        self.assertEqual(dry_run["set_count"], 2)
        self.assertIsNone(self.db.get(models.Character, 1).representative_template_filename)

        applied = initialize_representative_templates(self.db, self.temp.name, apply=True)
        self.db.commit()
        self.assertEqual(applied["target_characters"], 3)
        self.assertEqual(applied["set_count"], 2)
        self.assertEqual(self.db.get(models.Character, 1).representative_template_filename, "char_1_001.png")
        self.assertEqual(self.db.get(models.Character, 2).representative_template_filename, "char_2.png")
        self.assertEqual(self.db.get(models.Character, 4).representative_template_filename, "char_4_009.png")

        repeated = initialize_representative_templates(self.db, self.temp.name, apply=True)
        self.assertEqual(repeated["target_characters"], 1)
        self.assertEqual(repeated["set_count"], 0)
        self.assertEqual(repeated["no_candidate"], [3])

    def test_reports_ambiguous_oldest_generation_and_invalid_files(self):
        for filename in ("char_1.png", "char_1_000.png", "bad.png", "char_99_001.png"):
            (self.templates / filename).write_bytes(filename.encode())

        report = initialize_representative_templates(self.db, self.temp.name, apply=True)

        self.assertEqual(report["set_count"], 0)
        self.assertEqual(report["unset_count"], 3)
        self.assertEqual(report["invalid_files"], ["bad.png"])
        self.assertEqual(report["ambiguous_generation"][0]["character_id"], 1)
        self.assertEqual(report["ambiguous_generation"][0]["generation"], 0)
        self.assertEqual(report["unknown_character_files"], ["char_99_001.png"])
        self.assertIsNone(self.db.get(models.Character, 1).representative_template_filename)


if __name__ == "__main__":
    unittest.main()
