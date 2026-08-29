"""Phase 2A regression tests for backward-compatible schema expansion."""

from contextlib import redirect_stdout
from datetime import date
from io import StringIO
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if "database" in sys.modules and not hasattr(sys.modules["database"], "Base"):
    for module_name in ("schemas", "models", "database"):
        sys.modules.pop(module_name, None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from database import Base, SessionLocal, engine  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402


class Phase2AModelAndSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _tournament(self, name, creator=None, **values):
        tournament = models.Tournament(
            name=name,
            date=date(2026, 1, 1),
            created_by=creator.id if creator else None,
            **values,
        )
        self.db.add(tournament)
        self.db.flush()
        return tournament

    def test_scope_defaults_to_full64_and_schema_rejects_invalid_value(self):
        tournament = self._tournament("default scope")
        self.db.commit()
        self.db.refresh(tournament)
        self.assertEqual(tournament.registration_scope, "full_64")
        response = schemas.Tournament.model_validate(tournament)
        self.assertEqual(response.registration_scope, "full_64")
        self.assertIsNone(response.provider_game_start_date)
        self.assertEqual(
            schemas.TournamentBase(name="schema default", date=date(2026, 1, 1)).registration_scope,
            "full_64",
        )
        with self.assertRaises(ValidationError):
            schemas.TournamentBase(
                name="invalid scope",
                date=date(2026, 1, 1),
                registration_scope="other",
            )
        self.db.add(models.Tournament(
            name="database invalid scope",
            date=date(2026, 1, 1),
            registration_scope="other",
        ))
        with self.assertRaises(IntegrityError):
            self.db.commit()

    def test_legacy_inputs_may_omit_all_new_nullable_fields(self):
        tournament_input = schemas.TournamentBase(
            name="legacy tournament input",
            date=date(2026, 1, 1),
        )
        self.assertEqual(tournament_input.model_dump(), {
            "name": "legacy tournament input",
            "date": date(2026, 1, 1),
            "season": None,
            "owner_name": None,
            "championship_id": None,
            "registration_scope": "full_64",
            "provider_game_start_date": None,
        })
        self.assertNotIn("registration_scope", tournament_input.model_fields_set)
        self.assertNotIn(
            "registration_scope",
            tournament_input.model_dump(exclude_unset=True),
        )

        player_input = schemas.PlayerBase(
            tournament_id=1,
            name="legacy player input",
            seed_number=1,
        )
        self.assertIsNone(player_input.champion_slot)
        self.assertIsNone(player_input.model_dump()["champion_slot"])

        match_input = schemas.MatchBase(
            tournament_id=1,
            stage="Best 64",
            attacker_id=1,
            defender_id=2,
        )
        self.assertIsNone(match_input.bracket_stage)
        self.assertIsNone(match_input.bracket_slot)
        self.assertIsNone(match_input.model_dump()["bracket_stage"])
        self.assertIsNone(match_input.model_dump()["bracket_slot"])

        tournament = self._tournament("nullable response")
        players = [
            models.Player(tournament_id=tournament.id, name="Player 1", seed_number=1),
            models.Player(tournament_id=tournament.id, name="Player 2", seed_number=2),
        ]
        self.db.add_all(players)
        self.db.flush()
        match = models.Match(
            tournament_id=tournament.id,
            stage="Best 64",
            attacker_id=players[0].id,
            defender_id=players[1].id,
        )
        self.db.add(match)
        self.db.commit()

        tournament_response = schemas.Tournament.model_validate(tournament)
        player_response = schemas.Player.model_validate(players[0])
        match_response = schemas.Match.model_validate(match)
        self.assertIsNone(tournament_response.provider_game_start_date)
        self.assertIsNone(player_response.champion_slot)
        self.assertIsNone(match_response.bracket_stage)
        self.assertIsNone(match_response.bracket_slot)

    def test_provider_game_start_date_is_a_stored_snapshot(self):
        creator = models.AppUser(
            email="provider@example.invalid",
            hashed_password="unused",
            game_start_date=date(2024, 2, 3),
            approval_status="approved",
        )
        self.db.add(creator)
        self.db.flush()
        tournament = self._tournament(
            "stored provider date",
            creator,
            provider_game_start_date=creator.game_start_date,
        )
        self.db.commit()

        creator.game_start_date = date(2025, 4, 5)
        self.db.commit()
        self.db.refresh(tournament)
        self.assertEqual(tournament.provider_game_start_date, date(2024, 2, 3))

        no_creator = self._tournament("no creator")
        creator_without_date = models.AppUser(
            email="provider-no-date@example.invalid",
            hashed_password="unused",
            game_start_date=None,
            approval_status="approved",
        )
        self.db.add(creator_without_date)
        self.db.flush()
        no_profile_date = self._tournament("no profile date", creator_without_date)
        self.db.commit()
        self.assertIsNone(no_creator.provider_game_start_date)
        self.assertIsNone(no_profile_date.provider_game_start_date)

    def test_champion_slot_range_uniqueness_and_null_compatibility(self):
        first_tournament = self._tournament("first", registration_scope="champion_8")
        second_tournament = self._tournament("second", registration_scope="champion_8")
        self.db.add_all([
            models.Player(tournament_id=first_tournament.id, name="slot 1", champion_slot=1),
            models.Player(tournament_id=first_tournament.id, name="slot 8", champion_slot=8),
            models.Player(tournament_id=first_tournament.id, name="null one", champion_slot=None),
            models.Player(tournament_id=first_tournament.id, name="null two", champion_slot=None),
            models.Player(tournament_id=second_tournament.id, name="other tournament slot 1", champion_slot=1),
        ])
        self.db.commit()

        for invalid_slot in (0, 9):
            self.db.add(models.Player(
                tournament_id=second_tournament.id,
                name=f"invalid {invalid_slot}",
                champion_slot=invalid_slot,
            ))
            with self.assertRaises(IntegrityError):
                self.db.commit()
            self.db.rollback()

        self.db.add(models.Player(
            tournament_id=first_tournament.id,
            name="duplicate slot 1",
            champion_slot=1,
        ))
        with self.assertRaises(IntegrityError):
            self.db.commit()

    def test_match_bracket_fields_uniqueness_and_legacy_nulls(self):
        tournament = self._tournament("matches")
        players = [
            models.Player(tournament_id=tournament.id, name=f"Player {number}", seed_number=number)
            for number in range(1, 5)
        ]
        self.db.add_all(players)
        self.db.flush()
        schema_match = schemas.MatchBase(
            tournament_id=tournament.id,
            stage="Best 8",
            attacker_id=players[0].id,
            defender_id=players[1].id,
            bracket_stage="quarterfinal",
            bracket_slot=1,
        )
        self.assertEqual((schema_match.bracket_stage, schema_match.bracket_slot), ("quarterfinal", 1))
        with self.assertRaises(ValidationError):
            schemas.MatchBase(
                tournament_id=tournament.id,
                stage="invalid",
                attacker_id=players[0].id,
                defender_id=players[1].id,
                bracket_stage="group",
                bracket_slot=1,
            )
        self.db.add_all([
            models.Match(
                tournament_id=tournament.id,
                stage="legacy",
                attacker_id=players[0].id,
                defender_id=players[1].id,
                winner_id=players[0].id,
            ),
            models.Match(
                tournament_id=tournament.id,
                stage="another legacy match",
                attacker_id=players[1].id,
                defender_id=players[2].id,
                winner_id=players[1].id,
            ),
            models.Match(
                tournament_id=tournament.id,
                stage="Best 8",
                bracket_stage="quarterfinal",
                bracket_slot=1,
                attacker_id=players[2].id,
                defender_id=players[3].id,
                winner_id=players[2].id,
            ),
        ])
        self.db.commit()

        stored = self.db.query(models.Match).filter_by(bracket_stage="quarterfinal", bracket_slot=1).one()
        self.assertEqual((stored.bracket_stage, stored.bracket_slot), ("quarterfinal", 1))

        self.db.add(models.Match(
            tournament_id=tournament.id,
            stage="duplicate",
            bracket_stage="quarterfinal",
            bracket_slot=1,
            attacker_id=players[0].id,
            defender_id=players[2].id,
        ))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

        self.db.add(models.Match(
            tournament_id=tournament.id,
            stage="invalid bracket stage",
            bracket_stage="group",
            bracket_slot=2,
            attacker_id=players[0].id,
            defender_id=players[3].id,
        ))
        with self.assertRaises(IntegrityError):
            self.db.commit()


class Phase2AMigrationTest(unittest.TestCase):
    revision = "e6b8c1d2f3a4"
    parent_revision = "c2f7a9b4d6e8"

    def _config(self, database_url):
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        config.set_main_option("sqlalchemy.url", database_url)
        return config

    def test_sqlite_upgrade_backfill_constraints_and_downgrade(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "phase2a.sqlite"
            connection = sqlite3.connect(database_path)
            connection.executescript("""
                CREATE TABLE app_users (
                    id INTEGER PRIMARY KEY,
                    game_start_date DATE
                );
                CREATE TABLE tournaments (
                    id INTEGER PRIMARY KEY,
                    created_by INTEGER
                );
                CREATE TABLE players (
                    id INTEGER PRIMARY KEY,
                    tournament_id INTEGER
                );
                CREATE TABLE matches (
                    id INTEGER PRIMARY KEY,
                    tournament_id INTEGER
                );
                INSERT INTO app_users (id, game_start_date) VALUES (1, '2024-02-03'), (2, NULL);
                INSERT INTO tournaments (id, created_by) VALUES
                    (10, 1), (11, 2), (12, NULL), (13, 999);
                INSERT INTO players (id, tournament_id) VALUES (100, 10), (101, 10);
                INSERT INTO matches (id, tournament_id) VALUES (200, 10), (201, 10);
            """)
            connection.commit()
            connection.close()

            database_url = f"sqlite:///{database_path.as_posix()}"
            config = self._config(database_url)
            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.stamp(config, self.parent_revision)
                command.upgrade(config, self.revision)

            migration_engine = create_engine(database_url)
            migration_inspector = inspect(migration_engine)
            self.assertIn("registration_scope", {column["name"] for column in migration_inspector.get_columns("tournaments")})
            self.assertIn("champion_slot", {column["name"] for column in migration_inspector.get_columns("players")})
            self.assertIn("bracket_stage", {column["name"] for column in migration_inspector.get_columns("matches")})
            self.assertIn("bracket_slot", {column["name"] for column in migration_inspector.get_columns("matches")})

            with migration_engine.begin() as migrated:
                rows = migrated.execute(text(
                    "SELECT id, registration_scope, provider_game_start_date FROM tournaments ORDER BY id"
                )).all()
                self.assertEqual(rows, [
                    (10, "full_64", "2024-02-03"),
                    (11, "full_64", None),
                    (12, "full_64", None),
                    (13, "full_64", None),
                ])
                migrated.execute(text("UPDATE players SET champion_slot = 1 WHERE id = 100"))
                migrated.execute(text("UPDATE players SET champion_slot = NULL WHERE id = 101"))
                migrated.execute(text("UPDATE matches SET bracket_stage = 'quarterfinal', bracket_slot = 1 WHERE id = 200"))

            with self.assertRaises(IntegrityError):
                with migration_engine.begin() as migrated:
                    migrated.execute(text("UPDATE players SET champion_slot = 9 WHERE id = 101"))
            with self.assertRaises(IntegrityError):
                with migration_engine.begin() as migrated:
                    migrated.execute(text("UPDATE players SET champion_slot = 1 WHERE id = 101"))
            with self.assertRaises(IntegrityError):
                with migration_engine.begin() as migrated:
                    migrated.execute(text(
                        "UPDATE matches SET bracket_stage = 'quarterfinal', bracket_slot = 1 WHERE id = 201"
                    ))

            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.downgrade(config, self.parent_revision)
            migration_inspector = inspect(migration_engine)
            self.assertNotIn("registration_scope", {column["name"] for column in migration_inspector.get_columns("tournaments")})
            self.assertNotIn("champion_slot", {column["name"] for column in migration_inspector.get_columns("players")})
            self.assertNotIn("bracket_stage", {column["name"] for column in migration_inspector.get_columns("matches")})
            migration_engine.dispose()

    def test_postgresql_15_offline_sql_contains_all_columns_and_constraints(self):
        config = self._config("postgresql://postgres:password@localhost/test")
        output = StringIO()
        with redirect_stdout(output):
            command.upgrade(
                config,
                f"{self.parent_revision}:{self.revision}",
                sql=True,
            )
        sql = output.getvalue()
        for expected in (
            "registration_scope", "provider_game_start_date", "champion_slot",
            "bracket_stage", "bracket_slot", "ck_tournament_registration_scope",
            "uq_player_tournament_champion_slot", "uq_match_tournament_bracket_slot",
        ):
            self.assertIn(expected, sql)


if __name__ == "__main__":
    unittest.main()
