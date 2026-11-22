"""Exercise the legacy save and publication APIs with independent PostgreSQL connections."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import event, text

import main
import models
from auth import create_access_token
from database import Base, SessionLocal, engine


class LegacyDeckRegistrationTest(TestCase):
    def setUp(self):
        if engine.dialect.name != "postgresql":
            self.skipTest("requires disposable PostgreSQL")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(main, "UPLOAD_DIR", str(root)))
        self.enterContext(patch.object(main, "PLAYER_ICONS_DIR", root / "player_icons"))
        self.enterContext(patch.object(main, "recompute_snapshot"))
        self.addCleanup(main._dashboard_cache.clear)
        main._dashboard_cache.clear()
        with SessionLocal() as db:
            db.add_all([
                models.AppUser(id=1, email="owner@example.invalid", hashed_password="unused",
                               role="contributor", approval_status="active"),
                models.AppUser(id=2, email="admin@example.invalid", hashed_password="unused",
                               role="admin", approval_status="active"),
            ])
            db.flush()
            db.add(models.Tournament(id=1, name="Beta", date=date(2026, 11, 21),
                                     registration_scope="full_64", created_by=1))
            db.add_all(models.Character(id=cid, name=f"Nikke {cid}") for cid in range(1, 28))
            db.commit()

    def client(self, user_id):
        token = create_access_token({"sub": str(user_id)})
        client = TestClient(main.app, headers={"Authorization": f"Bearer {token}"})
        self.addCleanup(client.close)
        return client

    def save(self, seed=1, teams=None):
        return self.client(1).post("/api/tournaments/1/teams", json={
            "seed_number": seed, "teams": self.decks() if teams is None else teams,
        })

    def publish(self):
        return self.client(2).put("/api/tournaments/1/publication", json={"published": True})

    @staticmethod
    def decks():
        return [
            {"team_number": number, "characters": [
                {"id": (number - 1) * 5 + offset} for offset in range(1, 6)
            ]}
            for number in range(1, 6)
        ]

    def saved_decks(self, seed):
        with SessionLocal() as db:
            player = db.query(models.Player).filter_by(tournament_id=1, seed_number=seed).one_or_none()
            if player is None:
                return None
            return [
                (deck.id, [(row.team_number, *(getattr(row, f"char{i}_id") for i in range(1, 6)))
                           for row in sorted(deck.teams, key=lambda team: team.team_number)])
                for deck in player.deck_sets
            ]

    def wait_for_blocker(self, pid):
        # Check PostgreSQL directly so a slow request alone does not count as waiting.
        until = monotonic() + 5
        while monotonic() < until:
            with engine.connect() as connection:
                if connection.scalar(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_stat_activity
                        WHERE datname = current_database() AND :pid = ANY(pg_blocking_pids(pid))
                    )
                """), {"pid": pid}):
                    return
            sleep(0.025)
        self.fail(f"No request waited for PostgreSQL connection {pid}")

    def test_invalid_payload_and_failed_insert_leave_empty_seed_and_old_decks_intact(self):
        self.assertEqual(self.save(1).status_code, 200)
        original = self.saved_decks(1)
        self.assertEqual(len(original[0][1]), 5)
        bad_reference = self.decks()
        bad_reference[-1]["characters"][-1]["id"] = 10000
        for seed, expected in ((2, None), (1, original)):
            with self.subTest(seed=seed):
                self.assertEqual(self.save(seed, []).status_code, 400)
                self.assertEqual(self.saved_decks(seed), expected)
                # The foreign-key error is raised after the old DeckTeams were deleted in the transaction.
                with patch("traceback.print_exc"):
                    failure = self.save(seed, bad_reference)
                self.assertEqual(failure.status_code, 500, failure.text)
                self.assertEqual(self.saved_decks(seed), expected)

        changed = self.decks()
        changed[-1]["characters"][-1]["id"] = 26
        updated = self.save(1, changed)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertTrue(updated.json()["is_update"])
        saved = self.saved_decks(1)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0][1][-1][-1], 26)

    def test_publish_waits_for_first_deck_save_then_reads_the_completed_registration(self):
        writing, resume = Event(), Event()
        connection_ids = []

        def pause_before_insert(conn, _cursor, statement, _parameters, _context, _executemany):
            if statement.startswith("INSERT INTO deck_teams"):
                connection_ids.append(conn.connection.driver_connection.get_backend_pid())
                writing.set()
                if not resume.wait(8):
                    raise TimeoutError("Legacy deck write was not released")

        event.listen(engine, "before_cursor_execute", pause_before_insert)
        self.addCleanup(event.remove, engine, "before_cursor_execute", pause_before_insert)
        with ThreadPoolExecutor(max_workers=2) as pool:
            save = pool.submit(self.save)
            try:
                self.assertTrue(writing.wait(5))
                publish = pool.submit(self.publish)
                self.wait_for_blocker(connection_ids[0])
                self.assertFalse(publish.done())
                self.assertIsNone(self.saved_decks(1))
            finally:
                resume.set()
            saved, result = save.result(8), publish.result(8)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["publication_status"], "published")
        self.assertEqual(result.json()["readiness"]["complete_player_count"], 1)

    def test_publish_first_rejects_the_waiting_deck_update_without_replacing_it(self):
        self.assertEqual(self.save().status_code, 200)
        previous = self.saved_decks(1)
        publishing, resume = Event(), Event()
        connection_ids = []
        original = main.get_publication_readiness

        def pause_readiness(tournament, db):
            connection_ids.append(db.connection().connection.driver_connection.get_backend_pid())
            publishing.set()
            if not resume.wait(8):
                raise TimeoutError("Legacy publication was not released")
            return original(tournament, db)

        changed = self.decks()
        changed[-1]["characters"][-1]["id"] = 26
        with patch.object(main, "get_publication_readiness", pause_readiness), ThreadPoolExecutor(max_workers=2) as pool:
            publish = pool.submit(self.publish)
            try:
                self.assertTrue(publishing.wait(5))
                save = pool.submit(self.save, 1, changed)
                self.wait_for_blocker(connection_ids[0])
                self.assertFalse(save.done())
            finally:
                resume.set()
            result, denied = publish.result(8), save.result(8)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(denied.json()["code"], "tournament_published")
        self.assertEqual(self.saved_decks(1), previous)
