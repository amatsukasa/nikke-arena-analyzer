"""Regression coverage for the first-stage Character endpoint optimizations."""

import os
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import event, func, text  # noqa: E402

from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402


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
            models.Character(
                id=character_id,
                name=f"Character {character_id}",
                rarity="SSR",
                is_template_available=character_id in {1, 2, 5},
                template_filename={1: "char_1_002.png", 2: "char_2_001.png", 5: "char_5.png"}.get(character_id),
                representative_template_filename={1: "char_1_001.png", 2: "char_2_001.png", 5: "char_5.png"}.get(character_id),
            )
            for character_id in range(1, 6)
        )
        tournament = models.Tournament(
            id=1,
            name="Character endpoint performance test",
            date=date(2026, 1, 1),
            registration_scope="full_64",
        )
        player = models.Player(id=1, tournament_id=1, seed_number=1, name="Player 1")
        deck_set = models.DeckSet(id=1, player_id=1)
        self.db.add_all((tournament, player, deck_set))
        self.db.flush()
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

    def test_endpoint_uses_two_selects_and_does_not_scan_templates(self):
        statements = []

        def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            with patch.object(main, "list_template_paths") as list_paths:
                rows = main.get_characters(self.db)
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

        self.assertEqual(len(statements), 2)
        list_paths.assert_not_called()
        by_id = {row.id: row for row in rows}
        self.assertEqual(by_id[1].template_filename, "char_1_002.png")
        self.assertEqual(by_id[1].representative_template_filename, "char_1_001.png")
        self.assertEqual(by_id[1].icon_url, "/api/char-icon/1.png?v=char_1_001")
        self.assertTrue(by_id[1].is_template_available)
        self.assertEqual(by_id[2].template_filename, "char_2_001.png")
        self.assertFalse(by_id[3].is_template_available)
        self.assertIsNone(by_id[3].template_filename)
        self.assertIsNone(by_id[3].icon_url)

    def test_response_contract_is_unchanged(self):
        row = main.get_characters(self.db)[0]
        self.assertEqual(
            set(row.model_dump()),
            {
                "id", "name", "weapon", "element", "burst_phase",
                "manufacturer", "rarity", "class_type",
                "is_arena_relevant",
                "is_template_available", "template_filename",
                "representative_template_filename", "icon_url",
                "created_at", "usage_count",
            },
        )

    def test_char_icon_uses_saved_filename_without_enumerating_templates(self):
        with patch.object(main, "list_template_paths") as list_paths:
            response = main.get_char_icon(1, self.db)

        list_paths.assert_not_called()
        self.assertEqual(Path(response.path).name, "char_1_001.png")

    def test_new_templates_never_change_representative_selection(self):
        character = self.db.get(models.Character, 3)
        self.assertIsNone(character.representative_template_filename)
        first = np.full((32, 32, 3), 20, dtype=np.uint8)
        second = np.full((32, 32, 3), 220, dtype=np.uint8)

        first_path = main.install_champion_character_template(3, first, self.db)
        self.assertIsNotNone(first_path)
        self.assertIsNone(character.representative_template_filename)

        character.representative_template_filename = first_path.name

        second_path = main.install_champion_character_template(3, second, self.db)
        self.assertIsNotNone(second_path)
        self.assertNotEqual(second_path.name, first_path.name)
        self.assertEqual(character.representative_template_filename, first_path.name)

    def test_arena_relevance_defaults_false_and_is_returned_without_extra_selects(self):
        marked = self.db.get(models.Character, 1)
        marked.is_arena_relevant = True
        self.db.commit()

        statements = []

        def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            rows = main.get_characters(self.db)
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

        by_id = {row.id: row for row in rows}
        self.assertTrue(by_id[1].is_arena_relevant)
        self.assertFalse(by_id[2].is_arena_relevant)
        self.assertEqual(len(statements), 2)

    def test_create_update_and_list_preserve_arena_relevance(self):
        if engine.dialect.name == "postgresql":
            self.db.execute(text(
                "SELECT setval(pg_get_serial_sequence('characters', 'id'), "
                "(SELECT MAX(id) FROM characters))"
            ))
            self.db.commit()

        created = main.create_character(
            {"name": "Arena API Character", "is_arena_relevant": True},
            object(),
            self.db,
        )
        character_id = created["character"]["id"]
        self.assertTrue(self.db.get(models.Character, character_id).is_arena_relevant)

        main.update_character(
            character_id,
            {"is_arena_relevant": False},
            object(),
            self.db,
        )
        listed = {row.id: row for row in main.get_characters(self.db)}
        self.assertFalse(listed[character_id].is_arena_relevant)


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

    def test_dashboard_has_all_arena_display_modes_without_an_extra_fetch(self):
        source = (BACKEND_DIR.parent / "frontend/src/app/tournament/[id]/dashboard/page.tsx").read_text(encoding="utf-8")
        picker = (BACKEND_DIR.parent / "frontend/src/components/SynergyCharacterPicker.tsx").read_text(encoding="utf-8")
        self.assertIn('useState<ArenaCharacterDisplayMode>("priority")', source)
        self.assertIn("<ArenaCharacterDisplaySelect", source)
        self.assertIn('<option value="priority">', picker)
        self.assertIn('<option value="only">', picker)
        self.assertIn('<option value="all">', picker)
        self.assertEqual(source.count('fetch("/api/characters"'), 1)

    def test_admin_can_edit_arena_relevance(self):
        source = (BACKEND_DIR.parent / "frontend/src/app/admin/page.tsx").read_text(encoding="utf-8")
        self.assertIn("is_arena_relevant: formIsArenaRelevant", source)
        self.assertIn("アリーナ向けキャラクター", source)


if __name__ == "__main__":
    unittest.main()
