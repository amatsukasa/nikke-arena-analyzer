"""Private individual-tournament read boundary regression coverage."""

from datetime import date
import os
from pathlib import Path
import sys
import tempfile
import unittest


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402


class TournamentDetailAccessTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.normal = self._user("normal@example.invalid", "user")
        self.owner = self._user("owner@example.invalid", "contributor")
        self.other_owner = self._user("other@example.invalid", "contributor")
        self.admin = self._user("admin@example.invalid", "admin")
        self.tournaments = {}
        for scope in ("full_64", "champion_8"):
            for status in ("draft", "published"):
                tournament = models.Tournament(
                    name=f"{scope}-{status}",
                    date=date(2026, 8, 31),
                    registration_scope=scope,
                    publication_status=status,
                    created_by=self.owner.id,
                )
                self.db.add(tournament)
                self.db.flush()
                self.tournaments[(scope, status)] = tournament
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _user(self, email, role):
        user = models.AppUser(
            email=email,
            hashed_password="unused",
            role=role,
            approval_status="active",
        )
        self.db.add(user)
        self.db.flush()
        return user

    def _assert_hidden(self, callback):
        with self.assertRaises(HTTPException) as raised:
            callback()
        self.assertEqual(raised.exception.status_code, 404)
        self.assertNotIn("owner", str(raised.exception.detail).lower())

    def test_detail_and_dashboard_access_matrix_for_all_scopes_and_statuses(self):
        for (scope, status), tournament in self.tournaments.items():
            with self.subTest(scope=scope, status=status, viewer="anonymous"):
                self._assert_hidden(lambda: main.require_tournament_viewer(tournament.id, self.db, None))
            for viewer in (self.normal, self.other_owner):
                with self.subTest(scope=scope, status=status, viewer=viewer.role):
                    self._assert_hidden(lambda viewer=viewer: main.require_tournament_viewer(tournament.id, self.db, viewer))
                    self._assert_hidden(lambda viewer=viewer: main.require_tournament_dashboard_viewer(tournament.id, self.db, viewer))
            for viewer in (self.owner, self.admin):
                with self.subTest(scope=scope, status=status, viewer=viewer.role):
                    self.assertEqual(main.require_tournament_viewer(tournament.id, self.db, viewer).id, tournament.id)
                    self.assertEqual(main.require_tournament_dashboard_viewer(tournament.id, self.db, viewer).id, tournament.id)

    def test_null_created_by_is_admin_only(self):
        tournament = models.Tournament(
            name="legacy-null-owner", date=date(2026, 8, 31),
            registration_scope="full_64", publication_status="published", created_by=None,
        )
        self.db.add(tournament)
        self.db.commit()
        for viewer in (None, self.owner, self.other_owner, self.normal):
            self._assert_hidden(lambda viewer=viewer: main.require_tournament_viewer(tournament.id, self.db, viewer))
        self.assertEqual(main.require_tournament_viewer(tournament.id, self.db, self.admin).id, tournament.id)

    def test_endpoint_groups_use_private_viewer_before_returning_data(self):
        full = self.tournaments[("full_64", "published")]
        champion = self.tournaments[("champion_8", "published")]
        protected = (
            lambda viewer: main.get_tournament(full.id, self.db, viewer),
            lambda viewer: main.get_dashboard_summary(full.id, self.db, viewer),
            lambda viewer: main.get_tournament_bracket(full.id, self.db, viewer),
            lambda viewer: main.get_players(full.id, self.db, viewer),
            lambda viewer: main.get_dashboard_stats(full.id, db=self.db, current_user=viewer),
            lambda viewer: main.get_dashboard_matchups(full.id, db=self.db, current_user=viewer),
            lambda viewer: main.get_best8_decks(full.id, self.db, viewer),
            lambda viewer: main.get_dashboard_player_stats(full.id, db=self.db, current_user=viewer),
            lambda viewer: main.get_champion_slots(champion.id, self.db, viewer),
            lambda viewer: main.get_champion_bracket(champion.id, self.db, viewer),
        )
        for endpoint in protected:
            self._assert_hidden(lambda endpoint=endpoint: endpoint(None))
            self._assert_hidden(lambda endpoint=endpoint: endpoint(self.other_owner))
        self.assertEqual(main.get_tournament(full.id, self.db, self.owner).id, full.id)
        self.assertEqual(main.get_tournament(champion.id, self.db, self.admin).id, champion.id)

    def test_public_selector_stays_available_without_owner_metadata(self):
        rows = main.get_tournaments(False, self.db, None)
        self.assertEqual({row.id for row in rows}, {
            self.tournaments[("full_64", "published")].id,
            self.tournaments[("champion_8", "published")].id,
        })
        for row in rows:
            self.assertIsNone(row.created_by)
            self.assertIsNone(row.owner_name)
            self.assertIsNone(row.creator_email)

    def test_player_icon_is_not_served_to_anonymous_or_unrelated_viewers(self):
        tournament = self.tournaments[("champion_8", "published")]
        player = models.Player(
            tournament_id=tournament.id, champion_slot=1, seed_number=1,
            name="Player 1",
            icon_url=f"/api/uploads/player_icons/tournament_{tournament.id}/player_1.png",
        )
        self.db.add(player)
        self.db.commit()
        with tempfile.TemporaryDirectory() as directory:
            previous_upload_dir = main.UPLOAD_DIR
            try:
                main.UPLOAD_DIR = directory
                path = Path(directory) / "player_icons" / f"tournament_{tournament.id}" / "player_1.png"
                path.parent.mkdir(parents=True)
                path.write_bytes(b"not-a-real-image")
                relative = f"player_icons/tournament_{tournament.id}/player_1.png"
                self._assert_hidden(lambda: main.get_upload(relative, self.db, None))
                self._assert_hidden(lambda: main.get_upload(relative, self.db, self.other_owner))
                self.assertEqual(main.get_upload(relative, self.db, self.owner).status_code, 200)
                self.assertEqual(main.get_upload(relative, self.db, self.admin).status_code, 200)
            finally:
                main.UPLOAD_DIR = previous_upload_dir


if __name__ == "__main__":
    unittest.main()
