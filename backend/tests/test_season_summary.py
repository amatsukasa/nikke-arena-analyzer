"""Regression coverage for Summary scope, arithmetic, ranking and article references."""

from types import SimpleNamespace
from datetime import date
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from auth import create_access_token
from database import Base, get_db
from main import app
from services import season_summary


class SeasonSummaryMathTest(TestCase):
    def test_round_and_match_units_are_independent(self):
        def match(mid, attack, defense, winner, rounds):
            return SimpleNamespace(
                id=mid, tournament_id=206, attacker_id=attack, defender_id=defense, winner_id=winner,
                round_results=[SimpleNamespace(round_number=number, winner_id=pid) for number, pid in rounds],
            )

        initial = match(1, 1, 2, 1, [(1, 1), (1, 1), (2, 1), (3, 1), (4, 2), (5, 2)])
        undecided = match(2, 3, 4, None, [(1, 4), (2, None), (3, 3), (3, 4), (6, 3)])
        unknown = match(3, None, 5, 5, [(1, 5)])
        totals = season_summary.side_results([initial, initial, undecided, unknown])
        self.assertEqual(totals, {
            "rounds": {"attack": 3, "defense": 3, "total": 6},
            "matches": {"attack": 1, "defense": 0, "total": 1},
        })

    def test_rank_five_includes_ties_and_earlier_rates_distinguish_no_population(self):
        groups = {"league": [], "championship": [8], "final": [8]}

        def trends(ids, db, stage, finish, *, shared_matches):
            rows = [(1, 4), (2, 3), (3, 2), (4, 2), (5, 1), (6, 1)] if stage == "final" else [(1, 2)]
            return {"total_players": 8, "team_usage": [
                {"canonical_id": str(id), "character_ids": [id], "player_count": adoption}
                for id, adoption in rows
            ]}

        answer = season_summary.ranking_sections(None, groups, season_summary.STAGES, trends, [])
        self.assertEqual(answer["league"]["tournament_ids"], [])
        final = answer["final"]["teams"]
        self.assertEqual([row["rank"] for row in final], [1, 2, 3, 3, 5, 5])
        self.assertEqual(final[0]["earlier"]["championship"]["rate"], 25.0)
        self.assertEqual(final[1]["earlier"]["championship"]["rate"], 0.0)
        self.assertIsNone(final[1]["earlier"]["league"]["rate"])


class SeasonSummaryApiTest(TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)
        with self.session.begin() as db:
            db.add_all([
                models.AppUser(id=1, email="admin@example.test", role="admin", approval_status="active",
                               hashed_password="unused", play_server="JP"),
                models.AppUser(id=2, email="provider@example.test", role="contributor", approval_status="active",
                               hashed_password="unused", play_server="GLOBAL"),
                models.Character(id=47, name="センチ"),
                models.Championship(id=11, name="Season 1", deck_registration_phases=True, include_in_statistics=True),
                models.Championship(id=12, name="Season 1", deck_registration_phases=True, include_in_statistics=True),
                models.Championship(id=13, name="Beta", deck_registration_phases=False, include_in_statistics=True),
                models.Championship(id=14, name="Excluded", deck_registration_phases=True, include_in_statistics=False),
            ])
            for tid, title, mode, owner, status in (
                (200, 11, "full_64", 1, "published"),
                (206, 12, "full_64", 1, "published"),
                (207, 12, "champion_8", 1, "published"),
                (208, 12, "champion_8", 2, "published"),
                (209, 12, "full_64", 1, "draft"),
                (210, 13, "full_64", 1, "published"),
                (211, 14, "full_64", 1, "published"),
            ):
                db.add(models.Tournament(
                    id=tid, championship_id=title, name=str(tid), date=date(2026, 11, 21),
                    registration_scope=mode, created_by=owner, publication_status=status,
                ))

        def test_db():
            with self.session() as db:
                yield db

        self.enterContext(patch.dict(app.dependency_overrides, {get_db: test_db}))
        self.reader = TestClient(app)
        self.admin = TestClient(app, headers={"Authorization": f"Bearer {create_access_token({'sub': '1'})}"})
        self.provider = TestClient(app, headers={"Authorization": f"Bearer {create_access_token({'sub': '2'})}"})
        for client in (self.reader, self.admin, self.provider):
            self.addCleanup(client.close)

    def summary(self, title, server="JP"):
        response = self.reader.get(f"/api/season-summary/{title}", params={"play_server": server})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_public_scope_exact_title_server_stage_and_zero_cases(self):
        jp = self.summary(12)
        self.assertEqual((jp["tournament_ids"], jp["tournament_count"], jp["full_64"], jp["champion_8"]), ([206, 207], 2, 1, 1))
        self.assertEqual(jp["initial_stage"], "final")
        self.assertEqual(jp["rankings"]["league"]["tournament_ids"], [206])
        self.assertEqual(jp["rankings"]["championship"]["tournament_ids"], [206, 207])
        self.assertEqual(self.summary(11)["tournament_ids"], [200])
        gl = self.summary(12, "GLOBAL")
        self.assertEqual(gl["tournament_ids"], [208])
        self.assertEqual(gl["rankings"]["league"]["tournament_ids"], [])
        self.assertEqual(gl["rankings"]["final"]["tournament_ids"], [208])
        self.assertEqual(list(self.summary(13)["rankings"]), ["legacy"])
        self.assertEqual(self.summary(14)["tournament_ids"], [])
        self.assertEqual(self.summary(12, "KR")["rounds"]["total"], 0)
        self.assertEqual(self.reader.get("/api/articles/season/12").json()["latest"], None)

    def test_admin_debut_roster_omission_and_unadopted_character(self):
        edit = "/api/championships/12"
        self.assertEqual(self.provider.put(edit, json={"name": "Season 1", "debut_character_ids": [47]}).status_code, 403)
        self.assertEqual(self.admin.put(edit, json={"name": "Season 1", "debut_character_ids": [9999]}).status_code, 422)
        update = self.admin.put(edit, json={"name": "Season 1", "debut_character_ids": [47, 47]})
        self.assertEqual(update.json()["debut_character_ids"], [47])
        self.assertEqual(self.admin.put(edit, json={"name": "Season 1"}).json()["debut_character_ids"], [47])
        debut = self.summary(12)["debut"]
        self.assertEqual(debut["stage"], "championship")
        self.assertEqual(debut["tournament_ids"], [206, 207])
        self.assertEqual(debut["characters"], [
            {"id": 47, "name": "センチ", "count": 0, "population": 0, "rate": None,
             "wins": 0, "losses": 0, "rounds": 0, "win_rate": None},
        ])
        self.assertEqual(self.admin.put(edit, json={"name": "Season 1", "debut_character_ids": []}).status_code, 200)
        self.assertIsNone(self.summary(12)["debut"])

    def test_reference_capture_changes_only_on_explicit_capture_and_publication(self):
        body = {"kind": "season", "championship_id": 12, "title": "Note", "character_ids": [],
                "body": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Note"}]}]}}
        first = self.admin.post("/api/admin/articles", json={"draft": body, "publish": True}).json()
        article_path = f"/api/articles/{first['id']}"
        edit_path = f"/api/admin/articles/{first['id']}"
        self.assertNotIn("reference_scope", self.reader.get(article_path).json())
        captured = self.admin.put(edit_path, json={
            "draft": body, "reference_server": "JP", "revision": first["revision"],
        }).json()
        self.assertEqual(captured["draft"]["reference_scope"], {"play_server": "JP", "tournament_count": 2})
        self.assertNotIn("reference_scope", self.reader.get(article_path).json())
        published = self.admin.put(edit_path, json={
            "draft": captured["draft"], "publish": True, "revision": captured["revision"],
        }).json()
        with self.session.begin() as db:
            db.get(models.Tournament, 206).publication_status = "draft"
            db.get(models.Tournament, 207).publication_status = "draft"
            db.get(models.Tournament, 209).publication_status = "published"
        self.assertEqual(self.summary(12)["tournament_ids"], [209])
        corrected = self.admin.put(edit_path, json={
            "draft": {**body, "title": "Corrected", "reference_scope": {"play_server": "KR", "tournament_count": 999}},
            "publish": True, "revision": published["revision"],
        }).json()
        self.assertEqual(self.reader.get(article_path).json()["reference_scope"]["tournament_count"], 2)
        explicit = self.admin.put(edit_path, json={
            "draft": corrected["draft"], "reference_server": "JP", "revision": corrected["revision"],
        }).json()
        self.assertEqual(explicit["draft"]["reference_scope"]["tournament_count"], 1)
        self.assertEqual(self.reader.get(article_path).json()["reference_scope"]["tournament_count"], 2)
        self.admin.put(edit_path, json={"draft": explicit["draft"], "publish": True, "revision": explicit["revision"]})
        self.assertEqual(self.reader.get(article_path).json()["reference_scope"]["tournament_count"], 1)
