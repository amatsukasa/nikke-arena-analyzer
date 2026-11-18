"""Composition API parity, exact adoption counts, and weighted round history."""
from datetime import date
from pathlib import Path
import sys
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import auth
from database import Base, SessionLocal, engine
import main
import models
from services import arena_phases, cross_analytics

TARGET = "1,2,3,4,5"
OPPONENT = "6,7,8,9,10"


def seed_compositions(db, password):
    owner = models.AppUser(email="composition-review@example.invalid", hashed_password=auth.hash_password(password),
                           role="contributor", approval_status="active", play_server="JP")
    title = models.Championship(name="Composition acceptance", deck_registration_phases=True,
                               is_champion_arena=True, include_in_statistics=True)
    beta_title = models.Championship(name="Beta acceptance", deck_registration_phases=False,
                                    is_champion_arena=True, include_in_statistics=True)
    names = {1: "サクラ", 2: "編成A2", 6: "対戦相手B1"}
    db.add_all([owner, title, beta_title] + [models.Character(
        id=cid, name=names.get(cid, f"Character {cid}"), is_arena_relevant=True) for cid in range(1, 81)])
    db.flush()

    def teams(groups, reverse=False):
        return [{"team_number": i, "characters": [{"id": cid, "collection_level": "SR 10" if reverse else None}
                for cid in (reversed(group) if reverse else group)]} for i, group in enumerate(groups, 1)]

    groups = [list(range(n, n + 5)) for n in range(1, 81, 5)]

    def tournament(name, scope, title_row, published):
        row = models.Tournament(name=name, date=date(2026, 11, 18), season=title_row.name, championship_id=title_row.id,
            registration_scope=scope, created_by=owner.id,
            provider_game_start_date=date(2022, 11, 5 if name == "Same player twice" else 4),
            publication_status="published" if published else "draft")
        db.add(row)
        db.flush()
        return row

    def official(name, scope, published=True):
        full = scope == "full_64"
        t = tournament(name, scope, title, published)
        players = [models.Player(name=f"Seed {seed}", tournament_id=t.id, seed_number=seed,
                                 champion_slot=None if full else seed) for seed in range(1, 65 if full else 9)]
        db.add_all(players)
        db.flush()
        by_id = {p.id: p.seed_number for p in players}
        rounds = [64, 32, 16, 8, 4, 2] if full else [8, 4, 2]
        finalist = 33 if full else 5
        for remaining in rounds:
            phase = "final" if remaining == 2 else "best8" if full and remaining in (8, 4) else "initial"
            if remaining in (rounds[0], 2) or (full and remaining == 8):
                _, _, qualified, _ = arena_phases.context(t, db)
                for (pid, stage), qualification in qualified.items():
                    if stage != phase:
                        continue
                    seed = by_id[pid]
                    if phase == "final":
                        group_ids = [0 if seed == finalist else 1, 4, 5, 6, 7]
                    elif phase == "initial" and seed in ((1, finalist) if full else (finalist,)):
                        group_ids = [0, 8, 9, 10, 11]
                    elif phase == "initial":
                        group_ids = [1 if not full or seed in (34, 35) else 3, 8, 9, 10, 11]
                    else:
                        group_ids = [2, 8, 9, 10, 11]
                    # A replaced registration must not affect current adoption or history.
                    if phase == "initial" and seed == 1:
                        db.add(models.ArenaDeckRegistration(tournament_id=t.id, player_id=pid, phase=phase,
                            qualification=qualification, teams=teams([groups[i] for i in (12, 13, 14, 15, 11)])))
                        db.flush()
                    db.add(models.ArenaDeckRegistration(tournament_id=t.id, player_id=pid, phase=phase,
                        qualification=qualification, teams=teams([groups[i] for i in group_ids], phase == "final")))
                db.flush()
            _, nodes, _, _ = arena_phases.context(t, db)
            for node in nodes.values():
                if node["remaining"] != remaining:
                    continue
                a, d = node["participants"]
                winners = [a] * 5
                if full and remaining == 16 and by_id[a] in (1, finalist):
                    winners[0] = d
                db.add(models.ArenaMatchRevision(tournament_id=t.id, match_key=node["key"], phase=phase,
                    upstream=node["upstream"], attacker_id=a, defender_id=d, winner_id=a,
                    attacker_registration_id=node["registration_ids"][0], defender_registration_id=node["registration_ids"][1],
                    attacker_teams=node["teams"][0], defender_teams=node["teams"][1], rounds=winners))
            db.flush()
        return t

    full = official("Weighted 64", "full_64")
    eight = official("Same player twice", "champion_8")
    hidden = official("Private marker", "champion_8", False)
    beta = tournament("Beta marker", "full_64", beta_title, True)
    beta_players = []
    for seed, ids in ((1, (0, 8, 9, 10, 11)), (2, (1, 8, 9, 10, 11))):
        player = models.Player(name=f"Beta {seed}", seed_number=seed, tournament_id=beta.id)
        db.add(player)
        db.flush()
        beta_players.append(player.id)
        deck = models.DeckSet(player_id=player.id)
        for pos, idx in enumerate(ids, 1):
            deck.teams.append(models.DeckTeam(team_number=pos, **{f"char{i}_id": cid for i, cid in enumerate(groups[idx], 1)}))
        db.add(deck)
    attacker, defender = beta_players
    match = models.Match(tournament_id=beta.id, stage="Best 64", attacker_id=attacker,
                         defender_id=defender, winner_id=attacker)
    db.add(match)
    db.flush()
    db.add_all([models.RoundResult(match_id=match.id, round_number=number, winner_id=attacker)
                for number in range(1, 6)])
    db.commit()
    return owner, full, eight, hidden, beta


class CompositionAnalyticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        cls.db = SessionLocal()
        cls.addClassCleanup(cls.db.close)
        password = uuid4().hex
        owner, *tournaments = seed_compositions(cls.db, password)
        cls.full, cls.eight, cls.hidden, cls.beta = [t.id for t in tournaments]
        cls.title = tournaments[0].championship_id
        cls.public = TestClient(main.app)
        cls.private = TestClient(main.app)
        cls.addClassCleanup(cls.public.close)
        cls.addClassCleanup(cls.private.close)
        response = cls.private.post("/api/auth/login", json={"email": owner.email, "password": password})
        assert response.status_code == 200, response.text
        cross_analytics.clear_cache()

    def cross(self, ids, phase="all", **filters):
        response = self.public.post("/api/dashboard/cross-tournament/teams", json={
            "tournament_ids": ids, "registration_phase": phase, **filters})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def single(self, tid, phase="all", **filters):
        response = self.private.get(f"/api/tournaments/{tid}/dashboard/teams",
                                    params={"registration_phase": phase, **filters})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_weighted_rate_and_same_row_for_list_search_and_details(self):
        for phase, expected in (
            ("all", (2, 3, 4, 7, 57.1, "runner_up")),
            ("league", (2, 2, 4, 6, 66.7, "qualified_best8")),
            ("final", (1, 1, 0, 1, 0.0, "runner_up")),
        ):
            with self.subTest(phase=phase):
                listing = self.cross([self.full], phase, limit=100)["teams"]
                team = next(card for card in listing if card["canonical_id"] == TARGET)
                search = self.cross([self.full], phase, character_ids=[1])
                self.assertEqual(search, {"teams": [team], "total": 1})
                for detail in (self.cross([self.full], phase, detail_team=TARGET),
                               self.single(self.full, phase, detail_team=TARGET)):
                    self.assertEqual(detail["team"], team)
                    self.assertEqual(len(detail["matchups"]), expected[3])
                self.assertEqual(tuple(team[key] for key in ("count", "registration_count", "win_count",
                    "total_matches", "win_rate", "composition_best_result")), expected)

    def test_superseded_stage_registration_still_leaves_effective_rounds(self):
        player = self.db.query(models.Player).filter_by(tournament_id=self.eight, seed_number=5).one()
        registration = self.db.query(models.ArenaDeckRegistration).filter_by(
            tournament_id=self.eight, player_id=player.id, phase="initial").one()
        replacement = [{"team_number": 1, "characters": [
            {"id": cid, "collection_level": None} for cid in range(61, 66)]}, *registration.teams[1:]]
        latest = models.ArenaDeckRegistration(tournament_id=self.eight, player_id=player.id,
            phase="initial", qualification=registration.qualification, teams=replacement)
        self.db.add(latest)
        self.db.commit()
        try:
            self.assertEqual(self.cross([self.eight], "championship", character_ids=[1])["total"], 0)
            detail = self.cross([self.eight], detail_team=TARGET)
            team = detail["team"]
            self.assertEqual(team["registration_phases"], ["final"])
            self.assertEqual((team["count"], team["registration_count"], team["total_matches"]), (1, 1, 3))
            self.assertEqual(len(detail["matchups"]), 3)
        finally:
            self.db.delete(latest)
            self.db.commit()

    def test_adopter_deduplication_order_and_search_pagination(self):
        search = self.cross([self.eight], character_ids=[1], limit=1)
        self.assertEqual(search["total"], 1)
        self.assertEqual((search["teams"][0]["count"], search["teams"][0]["registration_count"]), (1, 2))
        self.assertEqual(self.cross([self.eight], character_ids=[1], limit=1, offset=1)["teams"], [])
        self.assertEqual(self.cross([self.eight], "league")["total"], 0)
        self.assertEqual(self.cross([self.eight], character_ids=[61])["total"], 0)
        detail = self.cross([self.eight], detail_team=TARGET)
        rows = [r for r in detail["matchups"] if OPPONENT in (r["canonical_attacker"], r["canonical_defender"])]
        order = [(r["registration_phase"], r["attacker_team"] if r["canonical_attacker"] == TARGET else r["defender_team"]) for r in rows]
        self.assertIn(("championship", [1, 2, 3, 4, 5]), order)
        self.assertIn(("final", [5, 4, 3, 2, 1]), order)

    def test_final_unique_teams_and_badges(self):
        final = self.cross([self.full], "final")
        self.assertEqual(final["total"], 6)
        self.assertEqual(sum(row["registration_count"] for row in final["teams"]), 10)
        self.assertEqual(sorted(row["composition_best_result"] for row in final["teams"]), ["champion"] * 5 + ["runner_up"])

    def test_opponent_history_keeps_two_league_wins_and_one_final_loss(self):
        for phase, wins, total in (("all", 2, 3), ("league", 2, 2), ("final", 0, 1)):
            rows = [row for row in self.cross([self.full], phase, detail_team=TARGET)["matchups"]
                    if OPPONENT in (row["canonical_attacker"], row["canonical_defender"])]
            self.assertEqual(len(rows), total)
            self.assertEqual(sum(row["winner_is_attacker"] == (row["canonical_attacker"] == TARGET)
                                 for row in rows), wins)

    def test_public_boundaries_and_existing_phase_contract(self):
        self.assertEqual(self.cross([self.full, self.hidden], character_ids=[1]),
                         self.cross([self.full], character_ids=[1]))
        self.assertEqual(self.cross([self.full], championship_id=self.title, play_server="JP",
                                    provider_game_start_date="2022-11-04")["total"],
                         self.cross([self.full])["total"])
        self.assertEqual(self.cross([self.full], provider_game_start_date="2022-11-05")["total"], 0)
        self.assertEqual(self.cross([self.beta], "league")["total"], 0)
        beta_card = self.cross([self.beta], character_ids=[1])["teams"][0]
        self.assertEqual(beta_card["registration_phases"], ["legacy"])
        self.assertEqual((beta_card["win_count"], beta_card["total_matches"], beta_card["win_rate"]), (1, 1, 100.0))
        self.assertEqual(self.cross([self.full, self.eight], play_server="JP",
                                    provider_game_start_date="2022-11-05", character_ids=[1]),
                         self.cross([self.eight], character_ids=[1]))
        self.assertEqual(self.cross([self.eight], character_usage=True)["character_usage"][0], {"id": 1, "count": 2})
        response = self.public.post("/api/dashboard/cross-tournament/stats", json={
            "tournament_ids": [self.full], "registration_phase": "all"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.json()["by_phase"]), {"legacy", "league", "championship", "final"})
