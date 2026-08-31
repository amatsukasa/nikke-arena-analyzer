"""Authorization regression coverage for administrative write endpoints."""

from datetime import date, datetime, timedelta, timezone
import hashlib
import inspect
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DASHBOARD_CACHE_TTL_SECONDS", "60")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import BackgroundTasks, HTTPException  # noqa: E402

import auth as auth_module  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402


class AdminApiAuthorizationTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.regular = self._user("regular@example.invalid", "user")
        self.contributor = self._user("contributor@example.invalid", "contributor")
        self.owner = self._user("owner@example.invalid", "contributor")
        self.admin = self._user("admin@example.invalid", "admin")
        self.championship = models.Championship(
            name="Existing championship",
            date=date(2026, 8, 1),
            created_by=self.admin.id,
        )
        self.db.add(self.championship)
        self.db.flush()
        self.full_tournament = models.Tournament(
            name="Full 64",
            date=date(2026, 8, 2),
            registration_scope="full_64",
            publication_status="published",
            created_by=self.owner.id,
        )
        self.champion_tournament = models.Tournament(
            name="Champion 8",
            date=date(2026, 8, 3),
            registration_scope="champion_8",
            publication_status="draft",
            created_by=self.owner.id,
        )
        self.db.add_all((self.full_tournament, self.champion_tournament))
        self.db.flush()
        self.full_snapshot = models.TournamentSnapshot(
            tournament_id=self.full_tournament.id,
            team_usage=[{"key": "full"}],
            char_stats=[{"id": 1}],
            matchups=[],
            total_players=64,
            total_matches=63,
        )
        self.champion_snapshot = models.TournamentSnapshot(
            tournament_id=self.champion_tournament.id,
            team_usage=[{"key": "champion"}],
            char_stats=[{"id": 2}],
            matchups=[],
            total_players=8,
            total_matches=7,
        )
        self.db.add_all((self.full_snapshot, self.champion_snapshot))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _user(self, email: str, role: str) -> models.AppUser:
        user = models.AppUser(
            email=email,
            hashed_password="unused",
            role=role,
            approval_status="active",
        )
        self.db.add(user)
        self.db.flush()
        return user

    def _snapshot_state(self):
        return [
            (
                snapshot.tournament_id,
                snapshot.team_usage,
                snapshot.char_stats,
                snapshot.matchups,
                snapshot.total_players,
                snapshot.total_matches,
            )
            for snapshot in self.db.query(models.TournamentSnapshot)
            .order_by(models.TournamentSnapshot.tournament_id)
            .all()
        ]

    def _assert_forbidden(self, user: models.AppUser):
        with self.assertRaises(HTTPException) as raised:
            auth_module.require_admin(user)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "管理者権限が必要です")

    def test_routes_use_shared_require_admin_dependency(self):
        for endpoint in (
            main.create_championship,
            main.update_championship,
            main.delete_championship,
            main.rebuild_tournament_snapshot,
        ):
            dependency = inspect.signature(endpoint).parameters["current_user"].default
            self.assertIs(dependency.dependency, auth_module.require_admin, endpoint.__name__)

    def test_unauthenticated_regular_contributor_and_owner_are_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            auth_module.get_current_user(None)
        self.assertEqual(raised.exception.status_code, 401)

        championship_before = (
            self.db.query(models.Championship).count(),
            self.championship.name,
            self.championship.date,
        )
        snapshots_before = self._snapshot_state()
        for user in (self.regular, self.contributor, self.owner):
            self._assert_forbidden(user)
        self.db.expire_all()
        championship = self.db.get(models.Championship, self.championship.id)
        self.assertEqual(
            (
                self.db.query(models.Championship).count(),
                championship.name,
                championship.date,
            ),
            championship_before,
        )
        self.assertEqual(self._snapshot_state(), snapshots_before)

    def test_admin_can_create_update_and_delete_championship(self):
        created = main.create_championship(
            schemas.ChampionshipCreate(name="Created", date=date(2026, 8, 4)),
            self.db,
            self.admin,
        )
        self.assertEqual(created.created_by, self.admin.id)

        updated = main.update_championship(
            created.id,
            schemas.ChampionshipCreate(name="Updated", date=date(2026, 8, 5)),
            self.db,
            self.admin,
        )
        self.assertEqual(updated.name, "Updated")
        self.assertEqual(updated.date, date(2026, 8, 5))

        response = main.delete_championship(created.id, self.db, self.admin)
        self.assertEqual(response, {"ok": True})
        self.assertIsNone(self.db.get(models.Championship, created.id))

    def test_admin_can_schedule_snapshot_rebuild_without_changing_snapshot_format(self):
        before = self._snapshot_state()
        for tournament in (self.full_tournament, self.champion_tournament):
            tasks = BackgroundTasks()
            response = main.rebuild_tournament_snapshot(
                tournament.id,
                tasks,
                self.db,
                self.admin,
            )
            self.assertTrue(response["ok"])
            self.assertEqual(len(tasks.tasks), 1)
        self.db.expire_all()
        self.assertEqual(self._snapshot_state(), before)

    def test_registration_stays_pending_contributor_and_requires_valid_one_time_token(self):
        with patch.object(main, "send_registration_request"):
            response = main.user_register(
                {
                    "email": "pending@example.invalid",
                    "password": "local-test-password",
                    "gameStartDate": "2026-08-01",
                    "role": "admin",
                },
                self.db,
            )
        self.assertEqual(response["status"], "pending")
        pending = self.db.query(models.AppUser).filter(
            models.AppUser.email == "pending@example.invalid"
        ).one()
        self.assertEqual(pending.role, "contributor")
        self.assertEqual(pending.approval_status, "pending")

        token = "one-time-local-test-token"
        pending.approval_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        pending.approval_requested_at = datetime.now(timezone.utc)
        self.db.commit()
        with self.assertRaises(HTTPException) as invalid:
            main.get_pending_registration(pending.id, "invalid-token", self.db)
        self.assertEqual(invalid.exception.status_code, 404)

        with patch.object(main, "send_registration_approved"):
            approved = main.approve_registration(
                {"userId": pending.id, "token": token},
                self.db,
            )
        self.assertTrue(approved["ok"])
        self.assertEqual(pending.approval_status, "active")
        self.assertIsNone(pending.approval_token_hash)
        with self.assertRaises(HTTPException) as reused:
            main.get_pending_registration(pending.id, token, self.db)
        self.assertEqual(reused.exception.status_code, 404)

        expired = self._user("expired@example.invalid", "contributor")
        expired.approval_status = "pending"
        expired.approval_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expired.approval_requested_at = datetime.now(timezone.utc) - timedelta(hours=73)
        self.db.commit()
        with self.assertRaises(HTTPException) as stale:
            main.get_pending_registration(expired.id, token, self.db)
        self.assertEqual(stale.exception.status_code, 410)

    def test_owner_boundaries_are_independent_from_the_removed_gate(self):
        # Published means available to cross-tournament aggregation, not that
        # the individual tournament is publicly viewable.
        with self.assertRaises(HTTPException) as published:
            main.require_tournament_viewer(self.full_tournament.id, self.db, None)
        self.assertEqual(published.exception.status_code, 404)
        with self.assertRaises(HTTPException) as draft:
            main.require_tournament_viewer(self.champion_tournament.id, self.db, None)
        self.assertEqual(draft.exception.status_code, 404)
        self.assertIs(
            main.require_tournament_viewer(
                self.full_tournament.id, self.db, self.owner
            ),
            self.full_tournament,
        )

        with self.assertRaises(HTTPException) as other_owner:
            main.require_tournament_manager(
                self.champion_tournament.id,
                self.db,
                self.contributor,
            )
        self.assertEqual(other_owner.exception.status_code, 403)
        self.assertIs(
            main.require_tournament_manager(
                self.champion_tournament.id,
                self.db,
                self.owner,
            ),
            self.champion_tournament,
        )


if __name__ == "__main__":
    unittest.main()
