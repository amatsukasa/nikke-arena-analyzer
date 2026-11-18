"""Canonical title settings, history protection, and migration regressions."""
from contextlib import redirect_stdout
from datetime import date
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from fastapi.testclient import TestClient
from database import Base, SessionLocal, engine, get_db
import auth
import main
import models
import schemas
from services import arena_phases, championship_settings, cross_analytics


class ChampionshipSettingsTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self.db = SessionLocal()
        self.admin = models.AppUser(email="title-admin@example.invalid", hashed_password="unused", role="admin", approval_status="active")
        self.owner = models.AppUser(email="title-owner@example.invalid", hashed_password="unused", role="contributor", approval_status="active")
        self.db.add_all([self.admin, self.owner])
        self.db.commit()
        main._dashboard_cache.clear()
        cross_analytics.clear_cache()

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.db.close()

    def title(self, **settings):
        values = dict(deck_registration_phases=True, is_champion_arena=True, include_in_statistics=True)
        values.update(settings)
        result = main.create_championship(schemas.ChampionshipCreate(name="Shared title", date=date(2026, 11, 17), **values), db=self.db, current_user=self.admin)
        return self.db.get(models.Championship, result["id"])

    def tournament(self, title, scope="full_64"):
        return main.create_tournament(schemas.TournamentBase(name="Dataset", date=date(2026, 11, 17), championship_id=title.id, registration_scope=scope), db=self.db, current_user=self.owner)

    def save(self, title, **changes):
        current = championship_settings.describe(title, championship_settings.children(self.db, title.id))
        values = {key: current[key] for key in championship_settings.FIELDS}
        values.update(changes)
        request = schemas.ChampionshipCreate(name=title.name, settings_revision=current["settings_revision"], apply_to_existing=True, **values)
        return main.update_championship(title.id, request, db=self.db, current_user=self.admin)

    def reject(self, status, operation):
        with self.assertRaises(HTTPException) as raised:
            operation()
        self.assertEqual(raised.exception.status_code, status)
        self.db.rollback()

    def test_create_edit_and_new_datasets_use_the_single_title(self):
        title = self.title()
        full = self.tournament(title)
        eight = self.tournament(title, "champion_8")
        self.assertTrue(full.deck_registration_phases)
        self.assertTrue(eight.deck_registration_phases)
        self.assertEqual(arena_phases.normalized_stage(full, "initial"), "league")
        self.assertEqual(arena_phases.normalized_stage(eight, "initial"), "championship")
        events = main.get_champion_arena_tournaments(self.db)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], f"championship:{title.id}")
        self.assertNotEqual(events[0]["id"], str(full.id))
        before = [(row.id, row.publication_status, row.legacy_deck_registration_phases) for row in (full, eight)]
        result = self.save(title, deck_registration_phases=False)
        self.assertFalse(result["deck_registration_phases"])
        self.db.expire_all()
        self.assertFalse(full.deck_registration_phases)
        self.assertFalse(eight.deck_registration_phases)
        self.assertEqual(arena_phases.normalized_stage(eight, "initial"), "legacy")
        self.assertEqual([(row.id, row.publication_status, row.legacy_deck_registration_phases) for row in (full, eight)], before)

    def test_statistics_scope_changes_without_touching_publication_or_dates(self):
        title = self.title()
        first, second = self.tournament(title), self.tournament(title)
        for row in (first, second):
            row.publication_status = "published"
            row.date = date(2025, 1, 2)
        self.db.commit()
        self.assertEqual(len(main.get_tournaments(False, self.db, None)), 2)
        revision = championship_settings.describe(title, [first, second])["settings_revision"]
        main.update_championship(title.id, schemas.ChampionshipCreate(name=title.name, date=title.date, include_in_statistics=False, settings_revision=revision, apply_to_existing=True), self.db, self.admin)
        self.assertEqual(main.get_tournaments(False, self.db, None), [])
        self.assertEqual(main.get_published_tournament_ids([first.id, second.id], self.db), [])
        self.assertTrue(all(row.publication_status == "published" and row.date == date(2025, 1, 2) for row in (first, second)))

    def test_provider_cannot_write_either_title_or_legacy_settings(self):
        title = self.title()
        tournament = self.tournament(title)
        for field in ("deck_registration_phases", "is_champion_arena", "has_match_data"):
            self.reject(403, lambda field=field: main.update_tournament(tournament.id, schemas.TournamentUpdate(**{field: False}), self.db, self.owner))
        main.update_tournament(tournament.id, schemas.TournamentUpdate(name="Provider label", provider_game_start_date=date(2022, 11, 4)), self.db, self.owner)
        self.assertTrue(tournament.deck_registration_phases)
        self.assertTrue(tournament.has_match_data)
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[auth.get_current_user] = lambda: self.owner
        client = TestClient(main.app)
        self.assertEqual(client.get("/api/admin/championships").status_code, 403)
        self.assertEqual(client.post("/api/championships", json={"name": "Not permitted", "deck_registration_phases": True}).status_code, 403)
        public = client.get("/api/championships").json()
        self.assertNotIn("deck_registration_phases", public[0])
        self.assertNotIn("include_in_statistics", public[0])

    def test_history_blocks_each_disabling_setting_and_keeps_data(self):
        title = self.title()
        tournament = self.tournament(title)
        player = models.Player(tournament_id=tournament.id, seed_number=1, name="Commander")
        self.db.add(player)
        self.db.flush()
        registration = models.ArenaDeckRegistration(tournament_id=tournament.id, player_id=player.id, phase="best8", qualification="existing", teams=[])
        self.db.add(registration)
        self.db.commit()
        registration_id = registration.id
        for field in championship_settings.FIELDS:
            self.reject(409, lambda field=field: self.save(title, **{field: False}))
            self.assertTrue(getattr(title, field))
            self.assertIsNotNone(self.db.get(models.ArenaDeckRegistration, registration_id))

    def test_legacy_conflict_requires_explicit_review_and_preserves_old_values(self):
        title = models.Championship(name="Legacy title", date=date(2026, 1, 1))
        self.db.add(title)
        self.db.flush()
        rows = [models.Tournament(name="Legacy", date=date(2026, 1, 1), championship_id=title.id, legacy_deck_registration_phases=value) for value in (False, True)]
        self.db.add_all(rows)
        self.db.commit()
        state = championship_settings.describe(title, rows)
        self.assertIn("deck_registration_phases", state["configuration_conflicts"])
        self.reject(409, lambda: self.tournament(title))
        result = self.save(title, deck_registration_phases=True, is_champion_arena=True, include_in_statistics=True)
        self.assertEqual(result["configuration_conflicts"], [])
        self.assertEqual([row.legacy_deck_registration_phases for row in rows], [False, True])
        self.assertTrue(all(row.deck_registration_phases for row in rows))

    def test_stale_settings_and_unconfirmed_propagation_are_rejected(self):
        title = self.title()
        tournament = self.tournament(title)
        state = championship_settings.describe(title, [tournament])
        unconfirmed = schemas.ChampionshipCreate(name=title.name, deck_registration_phases=False, settings_revision=state["settings_revision"])
        self.reject(409, lambda: main.update_championship(title.id, unconfirmed, self.db, self.admin))
        self.save(title, is_champion_arena=False)
        stale = schemas.ChampionshipCreate(name=title.name, deck_registration_phases=False, settings_revision=state["settings_revision"], apply_to_existing=True)
        self.reject(409, lambda: main.update_championship(title.id, stale, self.db, self.admin))
        self.assertTrue(tournament.deck_registration_phases)

    def test_title_revision_invalidates_cross_cache_and_private_key(self):
        title = self.title()
        tournament = self.tournament(title)
        calls = []
        def compute():
            calls.append(True)
            return {"formal": tournament.deck_registration_phases}
        self.assertTrue(cross_analytics.cached(self.db, [tournament.id], "all", "title-check", compute)["formal"])
        self.assertTrue(cross_analytics.cached(self.db, [tournament.id], "all", "title-check", compute)["formal"])
        self.assertEqual(len(calls), 1)
        main.set_private_dashboard_cache(tournament, "title-check", {"old": True})
        self.save(title, deck_registration_phases=False)
        self.assertFalse(cross_analytics.cached(self.db, [tournament.id], "all", "title-check", compute)["formal"])
        self.assertEqual(len(calls), 2)
        self.assertIsNone(main.get_private_dashboard_cache(tournament, "title-check"))

    def test_migration_is_repeatable_and_does_not_overwrite_conflicts_or_history(self):
        agreed = models.Championship(name="Agreed")
        conflicting = models.Championship(name="Conflicting")
        self.db.add_all([agreed, conflicting])
        self.db.flush()
        rows = [models.Tournament(name="Legacy", date=date(2026, 1, 1), championship_id=title.id, legacy_deck_registration_phases=value, publication_status="published") for title, value in ((agreed, False), (agreed, False), (conflicting, False), (conflicting, True))]
        self.db.add_all(rows)
        self.db.commit()
        spec = importlib.util.spec_from_file_location("title_settings_revision", Path(main.__file__).parent / "alembic/versions/e218a6c0d345_championship_arena_settings.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        operations = Operations(MigrationContext.configure(self.db.connection()))
        with patch.object(module, "op", operations), redirect_stdout(io.StringIO()):
            module.upgrade()
            self.db.expire_all()
            self.assertIs(agreed.deck_registration_phases, False)
            self.assertIsNone(conflicting.deck_registration_phases)
            module.upgrade()
        self.db.expire_all()
        self.assertEqual([row.legacy_deck_registration_phases for row in rows], [False, False, False, True])
        self.assertTrue(all(row.publication_status == "published" for row in rows))
        self.assertIs(agreed.deck_registration_phases, False)
        self.assertIsNone(conflicting.deck_registration_phases)

    def test_title_order_roundtrip_does_not_change_individual_metadata(self):
        title = self.title()
        row = self.tournament(title)
        row.display_order = 17
        self.db.commit()
        original_date = row.game_start_date
        saved = self.save(title, display_order=42)
        self.assertEqual(saved["display_order"], 42)
        self.db.expire_all()
        self.assertEqual(self.db.get(models.Championship, title.id).display_order, 42)
        self.assertEqual(row.display_order, 17)
        self.assertEqual(row.game_start_date, original_date)
        events = main.get_champion_arena_tournaments(db=self.db)
        self.assertEqual(next(event for event in events if event["championship_id"] == title.id)["display_order"], 42)
        self.assertIsNone(self.save(title, display_order=None)["display_order"])

    def test_title_order_migration_keeps_conflicting_legacy_values(self):
        agreed = self.title()
        conflicting = self.title()
        rows = [self.tournament(agreed), self.tournament(agreed), self.tournament(conflicting), self.tournament(conflicting)]
        for row, value in zip(rows, [12, 12, 13, 14]):
            row.display_order = value
        self.db.commit()
        spec = importlib.util.spec_from_file_location("title_order_revision", Path(main.__file__).parent / "alembic/versions/f329b7d1e456_championship_display_order.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, "op", Operations(MigrationContext.configure(self.db.connection()))), redirect_stdout(io.StringIO()):
            module.upgrade()
            module.upgrade()
        self.db.expire_all()
        self.assertEqual(agreed.display_order, 12)
        self.assertIsNone(conflicting.display_order)
        self.assertEqual([row.display_order for row in rows], [12, 12, 13, 14])
