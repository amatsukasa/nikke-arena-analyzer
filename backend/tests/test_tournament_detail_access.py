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

    def _add_player_icon(self, tournament, seed_number, relative_path, *, icon_url=None):
        player = models.Player(
            tournament_id=tournament.id,
            seed_number=seed_number,
            name=f"Player {seed_number}",
            icon_url=icon_url or f"/api/uploads/{relative_path}",
        )
        self.db.add(player)
        self.db.commit()
        return player

    @staticmethod
    def _write_upload(directory, relative_path):
        path = Path(directory) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not-a-real-image")
        return path

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
        with tempfile.TemporaryDirectory() as directory:
            previous_upload_dir = main.UPLOAD_DIR
            try:
                main.UPLOAD_DIR = directory
                relative = f"player_icons/tournament_{tournament.id}/player_1.png"
                self._add_player_icon(tournament, 1, relative)
                self._write_upload(directory, relative)
                self._assert_hidden(lambda: main.get_upload(relative, self.db, None))
                self._assert_hidden(lambda: main.get_upload(relative, self.db, self.other_owner))
                self.assertEqual(main.get_upload(relative, self.db, self.owner).status_code, 200)
                self.assertEqual(main.get_upload(relative, self.db, self.admin).status_code, 200)
            finally:
                main.UPLOAD_DIR = previous_upload_dir

    def test_full64_player_icon_accepts_exact_and_legacy_query_url_only_for_owner_or_admin(self):
        tournament = self.tournaments[("full_64", "published")]
        with tempfile.TemporaryDirectory() as directory:
            previous_upload_dir = main.UPLOAD_DIR
            try:
                main.UPLOAD_DIR = directory
                current_relative = f"player_icons/tournament_{tournament.id}/seed_8.png"
                legacy_relative = f"player_icons/tournament_{tournament.id}/seed_9.png"
                self._add_player_icon(tournament, 8, current_relative)
                self._add_player_icon(
                    tournament,
                    9,
                    legacy_relative,
                    icon_url=f"/api/uploads/{legacy_relative}?t=1786364273040",
                )
                self._write_upload(directory, current_relative)
                self._write_upload(directory, legacy_relative)

                for relative in (current_relative, legacy_relative):
                    with self.subTest(relative=relative, viewer="owner"):
                        self.assertEqual(main.get_upload(relative, self.db, self.owner).status_code, 200)
                    with self.subTest(relative=relative, viewer="admin"):
                        self.assertEqual(main.get_upload(relative, self.db, self.admin).status_code, 200)

                # Browsers never pass the query string into FastAPI's path
                # parameter; the legacy DB value above must still authorize
                # this normal asset request.
                self.assertEqual(main.get_upload(legacy_relative, self.db, self.owner).status_code, 200)
                for viewer in (None, self.normal, self.other_owner):
                    with self.subTest(viewer=getattr(viewer, "role", "anonymous")):
                        self._assert_hidden(lambda viewer=viewer: main.get_upload(legacy_relative, self.db, viewer))
            finally:
                main.UPLOAD_DIR = previous_upload_dir

    def test_player_icon_query_match_requires_exact_path_and_query_boundary(self):
        tournament = self.tournaments[("full_64", "draft")]
        with tempfile.TemporaryDirectory() as directory:
            previous_upload_dir = main.UPLOAD_DIR
            try:
                main.UPLOAD_DIR = directory
                relative = f"player_icons/tournament_{tournament.id}/seed_10.png"
                self._add_player_icon(
                    tournament,
                    10,
                    relative,
                    icon_url=f"/api/uploads/{relative}?t=old",
                )
                self._write_upload(directory, relative)
                similar = f"player_icons/tournament_{tournament.id}/seed_10.png-copy"
                no_boundary = f"player_icons/tournament_{tournament.id}/seed_10.png-old"
                self._write_upload(directory, similar)
                self._write_upload(directory, no_boundary)

                self._assert_hidden(lambda: main.get_upload(similar, self.db, self.owner))
                self._assert_hidden(lambda: main.get_upload(no_boundary, self.db, self.owner))
                self._assert_hidden(lambda: main.get_upload("player_icons/../templates/public.png", self.db, self.owner))
            finally:
                main.UPLOAD_DIR = previous_upload_dir

    def test_missing_unreferenced_and_null_owner_player_icons_stay_hidden(self):
        full = self.tournaments[("full_64", "draft")]
        null_owner = models.Tournament(
            name="legacy-null-owner-icon", date=date(2026, 8, 31),
            registration_scope="full_64", publication_status="published", created_by=None,
        )
        self.db.add(null_owner)
        self.db.commit()
        with tempfile.TemporaryDirectory() as directory:
            previous_upload_dir = main.UPLOAD_DIR
            try:
                main.UPLOAD_DIR = directory
                missing = f"player_icons/tournament_{full.id}/seed_11.png"
                self._add_player_icon(full, 11, missing)
                self._assert_hidden(lambda: main.get_upload(missing, self.db, self.owner))

                unreferenced = f"player_icons/tournament_{full.id}/seed_12.png"
                self._write_upload(directory, unreferenced)
                self._assert_hidden(lambda: main.get_upload(unreferenced, self.db, self.owner))

                legacy_relative = f"player_icons/tournament_{null_owner.id}/seed_1.png"
                self._add_player_icon(null_owner, 1, legacy_relative, icon_url=f"/api/uploads/{legacy_relative}?t=legacy")
                self._write_upload(directory, legacy_relative)
                self._assert_hidden(lambda: main.get_upload(legacy_relative, self.db, self.owner))
                self.assertEqual(main.get_upload(legacy_relative, self.db, self.admin).status_code, 200)

                template = "templates/public-template.png"
                self._write_upload(directory, template)
                self.assertEqual(main.get_upload(template, self.db, None).status_code, 200)
            finally:
                main.UPLOAD_DIR = previous_upload_dir


if __name__ == "__main__":
    unittest.main()
