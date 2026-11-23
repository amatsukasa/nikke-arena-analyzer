"""Regression coverage for Summary scope, arithmetic, ranking and article references."""

from collections import Counter
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
        totals, *_ = season_summary.side_results([initial, initial, undecided, unknown], {})
        self.assertEqual(totals, {
            "rounds": {"attack": 3, "defense": 3, "total": 6},
            "matches": {"attack": 1, "defense": 0, "total": 1},
        })

    def test_side_leaders_count_complete_compositions_in_each_side_of_mirrors(self):
        def team(number, *ids):
            return SimpleNamespace(team_number=number, **{f"char{i}_id": cid for i, cid in enumerate(ids, 1)})

        complete = (11, 12, 13, 14, 15)
        offense_only = (31, 32, 33, 34, 35)
        attack = SimpleNamespace(teams=[team(i, *complete) for i in range(1, 6)])
        defense = SimpleNamespace(teams=[team(i, *reversed(complete)) for i in range(1, 6)])
        next_attack = SimpleNamespace(teams=[team(i, *offense_only) for i in range(1, 6)])
        partial_defense = SimpleNamespace(teams=[
            team(i, 22, 22, 23, 9999, None) for i in range(1, 6)
        ])

        def match(mid, decks, phase):
            return SimpleNamespace(
                id=mid, tournament_id=206, attacker_id=1, defender_id=2, winner_id=1, arena_phase=phase,
                arena_decks=decks,
                round_results=[SimpleNamespace(round_number=i, winner_id=1 if i < 4 else 2) for i in range(1, 6)],
            )

        mirror = match(1, {1: attack, 2: defense}, "initial")
        other = match(2, {1: next_attack, 2: partial_defense}, "final")
        totals, character_counts, _, counts, wins = season_summary.side_results([mirror, mirror, other], {})
        self.assertEqual(totals["rounds"], {"attack": 6, "defense": 4, "total": 10})
        self.assertEqual(character_counts["defense"][22], 5)
        leaders = season_summary.side_leaders(counts, wins)
        self.assertEqual([row["character_ids"] for row in leaders["attack"]], [list(complete), list(offense_only)])
        self.assertEqual([row["character_ids"] for row in leaders["defense"]], [list(complete)])
        attack_row, = leaders["attack"][:1]
        defense_row, = leaders["defense"]
        self.assertEqual((attack_row["wins"], attack_row["losses"], attack_row["win_rate"]), (3, 2, 60.0))
        self.assertEqual((defense_row["wins"], defense_row["losses"], defense_row["win_rate"]), (2, 3, 40.0))

        season_summary.add_details_links(leaders, [{
            "canonical_id": "11,12,13,14,15", "attack_wins": 3, "attack_matches": 5,
            "win_count": 6, "total_matches": 11,
        }])
        self.assertTrue(attack_row["has_details"])
        self.assertFalse(defense_row["has_details"])
        self.assertFalse(leaders["attack"][1]["has_details"])

    def test_composition_rates_are_sorted_before_rounding_with_stable_ties(self):
        stages = ["1,2,3,4," + str(cid) for cid in range(5, 12)]
        counts = {"attack": Counter(dict(zip(stages, [5, 10, 10, 10, 1000, 9998, 4]))), "defense": Counter()}
        wins = {"attack": Counter(dict(zip(stages, [4, 8, 8, 8, 800, 7999, 4]))), "defense": Counter()}
        leaders = season_summary.side_leaders(counts, wins)
        self.assertEqual([row["canonical_id"] for row in leaders["attack"]],
                         [stages[i] for i in (5, 4, 1, 2, 3)])
        self.assertEqual({row["win_rate"] for row in leaders["attack"]}, {80.0})
        self.assertEqual(leaders["defense"], [])

    def test_partners_are_sorted_across_all_burst_types_using_team_registrations(self):
        usage = [
            {"character_ids": [47, 80, 9999, 51, 51], "count": 4},
            {"character_ids": [47, 13, 84, 51, 80], "count": 3},
            {"character_ids": [47, 13, 81, 81, 90], "count": 3},
            {"character_ids": [51, 53], "count": 99},
        ]
        values = season_summary.partner_counts(usage, {47})
        self.assertEqual(values[47][51], 7)
        self.assertNotIn(9999, values[47])
        counts = season_summary.character_section(8, 10, 6, 12, values[47], 10, {id: str(id) for id in values[47]})
        self.assertEqual([(row["id"], row["rate"]) for row in counts["partners"]], [(51, 70.0), (80, 70.0), (13, 60.0), (81, 30.0)])

    def test_overall_keeps_one_commander_who_registered_at_multiple_stages(self):
        def simulated_adoption(db, bulk, ids, stage, debut_ids, population, adopted):
            population.update((1, 2) if stage == "league" else (1,))
            adopted[47].add(1)

        def aggregate(ids, db, stage):
            return {"total_players": 2 if stage == "league" else 1,
                    "character_stats": [{"id": 47, "player_count": 1, "count": 1, "win_count": 1, "total_matches": 2}],
                    "team_usage": [{"character_ids": [47, 13 if stage == "league" else 20], "count": 1}]}

        with patch.object(season_summary, "adoption_by_commander", simulated_adoption):
            result = season_summary.debut_statistics(
                None, [47], {"league": [206], "championship": [206]}, ("league", "championship"), "championship",
                aggregate, {}, {47: "センチ", 13: "ノア", 20: "ネオン"},
                {"attack": Counter({47: 2}), "defense": Counter({47: 2})},
                {"attack": Counter({47: 1}), "defense": Counter({47: 1})},
            )
        sections = result["characters"][0]["sections"]
        self.assertEqual((sections["all"]["count"], sections["all"]["population"], sections["all"]["rate"]), (1, 2, 50.0))
        self.assertEqual(sections["all"]["rounds"], 4)
        self.assertEqual([row["rate"] for row in sections["all"]["partners"]], [50.0, 50.0])
        self.assertEqual(sections["championship"]["partners"][0]["rate"], 100.0)

    def test_rank_five_includes_ties_and_earlier_rates_distinguish_no_population(self):
        groups = {"league": [], "championship": [8], "final": [8]}

        def trends(ids, db, stage, finish, *, shared_matches):
            rows = [(1, 4), (2, 3), (3, 2), (4, 2), (5, 1), (6, 1)] if stage == "final" else [(1, 2)]
            return {"total_players": 8, "team_usage": [
                {"canonical_id": str(id), "character_ids": [id], "player_count": adoption}
                for id, adoption in rows
            ]}

        data = season_summary.stage_trends(None, groups, season_summary.STAGES, trends, [])
        answer = season_summary.ranking_sections(groups, data)
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
        character = debut["characters"][0]
        self.assertEqual({key: value for key, value in character.items() if key != "sections"},
                         {"id": 47, "name": "センチ", "count": 0, "population": 0, "rate": None,
                          "wins": 0, "losses": 0, "rounds": 0, "win_rate": None})
        self.assertEqual(set(character["sections"]), {"all", "league", "championship", "final"})
        self.assertEqual(character["sections"]["all"]["partners"], [])
        self.assertEqual(debut["tournament_ids_by_stage"]["league"], [206])
        self.assertEqual(self.admin.put(edit, json={"name": "Season 1", "debut_character_ids": []}).status_code, 200)
        self.assertIsNone(self.summary(12)["debut"])
        self.assertEqual(self.admin.put("/api/championships/13", json={"name": "Beta", "debut_character_ids": [47]}).status_code, 200)
        beta = self.summary(13)["debut"]["characters"][0]["sections"]
        self.assertEqual(beta["all"], beta["legacy"])

    def add_registration(self, db, tournament_id, player_id, ids, *, revision=False):
        if db.get(models.Player, player_id) is None:
            db.add(models.Player(id=player_id, name=str(player_id), tournament_id=tournament_id,
                                 seed_number=player_id % 100, champion_slot=player_id % 100 if tournament_id == 207 else None))
            db.flush()
        teams = [ids[offset:offset + 5] for offset in range(0, len(ids), 5)]
        if revision:
            db.add(models.ArenaDeckRegistration(
                tournament_id=tournament_id, player_id=player_id, phase="initial", qualification="initial",
                teams=[{"team_number": number, "characters": [{"id": cid} for cid in team]}
                       for number, team in enumerate(teams, 1)],
            ))
        else:
            db.add(models.DeckSet(player_id=player_id, teams=[
                models.DeckTeam(team_number=number, **{f"char{slot}_id": cid for slot, cid in enumerate(team, 1)})
                for number, team in enumerate(teams, 1)
            ]))

    def test_weapon_shares_use_current_filled_slots_and_rank_across_stages(self):
        with self.session.begin() as db:
            ids = list(range(100, 125))
            db.add_all([models.Character(id=cid, name=str(cid), burst_phase="A" if cid == 100 else "2",
                                        weapon="SG" if cid < 106 else None if cid == 124 else "SR")
                        for cid in ids])
            self.add_registration(db, 210, 101, ids)
            self.add_registration(db, 206, 201, ids, revision=True)
            self.add_registration(db, 207, 202, ids)
            self.add_registration(db, 208, 203, ids)
            self.add_registration(db, 209, 204, ids)
            db.flush()
            self.add_registration(db, 206, 201, [47, *ids[1:-2], 9999, 124], revision=True)
            db.get(models.Character, 47).weapon = "SR"

        stats = self.summary(12)
        self.assertNotIn("season_comparison", stats)
        weapons = stats["weapon_adoption"]
        league, championship, final = [weapons["by_stage"][stage] for stage in season_summary.STAGES]
        self.assertEqual((league["slots"], championship["slots"], final["slots"]), (24, 25, 0))
        self.assertEqual((league["counts"]["SG"], championship["counts"]["SG"]), (5, 6))
        self.assertEqual((league["counts"]["unknown"], championship["counts"]["unknown"]), (1, 1))
        self.assertEqual(sum(league["counts"].values()), league["slots"])
        self.assertEqual(weapons["slots"], 49)
        self.assertEqual(weapons["rankings"]["SG"], [
            {"id": cid, "name": str(cid), "count": 2, "population": 49, "rate": 4.1}
            for cid in range(101, 106)
        ])
        self.assertEqual(self.summary(12, "GLOBAL")["weapon_adoption"]["slots"], 25)

        beta = self.summary(13)
        self.assertEqual(list(beta["weapon_adoption"]["by_stage"]), ["legacy"])
        self.assertEqual(beta["weapon_adoption"]["slots"], 25)
        groups = beta["burst_rankings"]["legacy"]["groups"]
        self.assertTrue(all(any(nikke["id"] == 100 for nikke in group) for group in groups.values()))

        with self.session.begin() as db:
            db.get(models.Tournament, 207).publication_status = "draft"
        remaining = self.summary(12)["weapon_adoption"]
        self.assertEqual(remaining["slots"], 24)
        self.assertEqual(remaining["by_stage"]["championship"]["slots"], 0)
        self.assertEqual(remaining["rankings"]["SG"][0]["count"], 1)

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
