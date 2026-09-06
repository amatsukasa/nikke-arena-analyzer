"""Regression coverage for the first-stage Character endpoint optimizations."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import event, func  # noqa: E402

from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from services import character_templates  # noqa: E402


class CharactersEndpointPerformanceTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_upload_dir = main.UPLOAD_DIR
        main.UPLOAD_DIR = self.tmp.name
        template_dir = Path(self.tmp.name) / "templates"
        template_dir.mkdir()
        (template_dir / "char_1.png").write_bytes(b"legacy")
        (template_dir / "char_1_001.png").write_bytes(b"first")
        (template_dir / "char_1_002.png").write_bytes(b"latest")
        (template_dir / "char_2_001.png").write_bytes(b"only")
        (template_dir / "char_5.png").write_bytes(b"legacy")
        (template_dir / "char_5_000.png").write_bytes(b"zero-generation")
        (template_dir / "ignored.png").write_bytes(b"ignored")

        self.db.add_all(
            models.Character(id=character_id, name=f"Character {character_id}", rarity="SSR")
            for character_id in range(1, 6)
        )
        self.db.add_all((
            models.DeckTeam(
                deck_set_id=1,
                team_number=1,
                char1_id=1,
                char2_id=2,
                char3_id=None,
                char4_id=1,
                char5_id=3,
            ),
            models.DeckTeam(
                deck_set_id=1,
                team_number=2,
                char1_id=4,
                char2_id=1,
                char3_id=2,
                char4_id=None,
                char5_id=1,
            ),
        ))
        self.db.commit()

    def tearDown(self):
        main.UPLOAD_DIR = self.previous_upload_dir
        self.db.close()
        self.tmp.cleanup()

    def _legacy_usage_counts(self):
        result = {}
        for index in range(1, 6):
            column = getattr(models.DeckTeam, f"char{index}_id")
            for character_id, count in self.db.query(column, func.count(column)).group_by(column).all():
                if character_id:
                    result[character_id] = result.get(character_id, 0) + count
        return result

    def test_usage_counts_match_legacy_for_every_slot_duplicates_and_nulls(self):
        expected = self._legacy_usage_counts()
        rows = main.get_characters(self.db)
        actual = {row.id: row.usage_count for row in rows}

        self.assertEqual(expected, {1: 4, 2: 2, 3: 1, 4: 1})
        self.assertEqual(actual, {1: 4, 2: 2, 3: 1, 4: 1, 5: 0})

    def test_endpoint_uses_two_selects_and_scans_templates_once(self):
        statements = []

        def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            with patch.object(
                character_templates,
                "list_template_paths",
                wraps=character_templates.list_template_paths,
            ) as list_paths:
                rows = main.get_characters(self.db)
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

        self.assertEqual(len(statements), 2)
        list_paths.assert_called_once_with(Path(self.tmp.name) / "templates")
        by_id = {row.id: row for row in rows}
        self.assertEqual(by_id[1].template_filename, "char_1_002.png")
        self.assertEqual(by_id[1].icon_url, "/api/char-icon/1.png?v=char_1_002")
        self.assertTrue(by_id[1].is_template_available)
        self.assertEqual(by_id[2].template_filename, "char_2_001.png")
        self.assertFalse(by_id[3].is_template_available)
        self.assertIsNone(by_id[3].template_filename)
        self.assertIsNone(by_id[3].icon_url)

    def test_inventory_matches_existing_representative_selection_rule(self):
        inventory = character_templates.get_character_template_inventory(self.tmp.name)
        for character_id in (1, 2, 5):
            self.assertEqual(
                inventory[character_id],
                character_templates.find_character_template(self.tmp.name, character_id),
            )

    def test_response_contract_is_unchanged(self):
        row = main.get_characters(self.db)[0]
        self.assertEqual(
            set(row.model_dump()),
            {
                "id", "name", "weapon", "element", "burst_phase",
                "manufacturer", "rarity", "class_type",
                "is_template_available", "template_filename", "icon_url",
                "created_at", "usage_count",
            },
        )


class CharactersFrontendFetchContractTest(unittest.TestCase):
    def test_top_page_has_one_filter_independent_character_fetch(self):
        source = (BACKEND_DIR.parent / "frontend/src/app/page.tsx").read_text(encoding="utf-8")
        self.assertEqual(source.count('fetch("/api/characters"'), 1)
        self.assertNotIn("/api/characters?t=", source)
        self.assertIn("const fetchCharacters = async () =>", source)
        self.assertIn("return () => controller.abort();\n  }, []);", source)

    def test_dashboard_character_fetch_does_not_depend_on_requested_tab(self):
        source = (BACKEND_DIR.parent / "frontend/src/app/tournament/[id]/dashboard/page.tsx").read_text(encoding="utf-8")
        self.assertEqual(source.count('fetch("/api/characters"'), 1)
        self.assertNotIn("/api/characters?t=", source)
        self.assertIn("}, [isFirstLoad, tournamentId]);", source)
        self.assertNotIn("`/api/characters", source[source.index("const urls = ["):source.index("];", source.index("const urls = ["))])


if __name__ == "__main__":
    unittest.main()
