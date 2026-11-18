"""Exercise legacy league results through both dashboard API entry points."""
from copy import deepcopy
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


TARGET = "14,94,107,109,147"


def seed_league(db, password):
    owner = models.AppUser(email="legacy-league@example.invalid", hashed_password=auth.hash_password(password),
                           role="contributor", approval_status="active", play_server="JP")
    title = models.Championship(name="Season 1", deck_registration_phases=True, is_champion_arena=True,
                                include_in_statistics=True)
    db.add_all([owner, title])
    db.flush()
    tournament = models.Tournament(name="Legacy League", championship_id=title.id, date=date(2026, 1, 1),
                                   registration_scope="full_64", created_by=owner.id, publication_status="published")
    db.add(tournament)
    db.flush()
    winner = models.Player(name="Winner", tournament_id=tournament.id, seed_number=1)
    loser = models.Player(name="Legacy player", tournament_id=tournament.id, seed_number=2)
    db.add_all([winner, loser])
    pools = [list(range(201, 226)), [1, 2, 3, 4, 5, 14, 94, 107, 109, 147, *range(31, 46)]]
    for character_id in pools[0] + pools[1]:
        db.add(models.Character(id=character_id, name=f"Character {character_id}", is_arena_relevant=True))
    db.flush()
    for player, pool in zip((winner, loser), pools):
        deck = models.DeckSet(player_id=player.id)
        db.add(deck)
        db.flush()
        for number in range(1, 6):
            ids = pool[(number - 1) * 5:number * 5]
            team = models.DeckTeam(deck_set_id=deck.id, team_number=number)
            for slot, character_id in enumerate(ids, 1):
                setattr(team, f"char{slot}_id", character_id)
                setattr(team, f"collection{slot}", None if number == slot == 1 else "SR 15")
            db.add(team)
    db.flush()
    _, nodes, _, _ = arena_phases.context(tournament, db)
    node = next(node for node in nodes.values() if node["participants"] == [winner.id, loser.id])
    rounds = [winner.id, loser.id, winner.id, winner.id, winner.id]
    arena_phases.save_result(tournament, node["key"], {
        "upstream": node["upstream"], "registration_ids": node["registration_ids"],
        "revision_id": node["revision_id"], "rounds": rounds,
    }, db)
    revision = db.query(models.ArenaMatchRevision).filter_by(tournament_id=tournament.id).one()
    return tournament, owner, revision


class LegacyLeagueAchievementTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self.db = SessionLocal()
        self.addCleanup(self.db.close)
        password = uuid4().hex
        self.tournament, owner, self.revision = seed_league(self.db, password)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.anonymous = TestClient(main.app)
        self.addCleanup(self.anonymous.close)
        login = self.client.post("/api/auth/login", json={"email": owner.email, "password": password})
        self.assertEqual(login.status_code, 200, login.text)

    def assert_achievement(self, expected):
        main._dashboard_cache.clear()
        cross_analytics.clear_cache()
        path = f"/api/tournaments/{self.tournament.id}/dashboard/teams"
        payload = {"tournament_ids": [self.tournament.id], "registration_phase": "league", "limit": 20}
        self.assertEqual(self.anonymous.get(path).status_code, 404)
        for result in (
            self.client.get(path, params={"registration_phase": "league", "limit": 20}),
            self.client.post("/api/dashboard/cross-tournament/teams", json=payload),
        ):
            self.assertEqual(result.status_code, 200, result.text)
            card = next(team for team in result.json()["teams"] if team["canonical_id"] == TARGET)
            self.assertEqual((card["count"], card["total_matches"], card["win_rate"]), (1, 1, 100.0))
            self.assertEqual(card["composition_best_result"], expected)

    def test_exact_legacy_snapshot_restores_best64_for_the_winning_team(self):
        self.assertIsNone(self.revision.defender_registration_id)
        self.assert_achievement("best64")

    def test_slot_order_collection_and_missing_collection_do_not_match(self):
        original = deepcopy(self.revision.defender_teams)
        for change in ("slot_order", "collection", "missing_collection", "character", "team_number", "missing_team"):
            with self.subTest(change=change):
                teams = deepcopy(original)
                slots = teams[0]["characters"]
                if change == "slot_order":
                    slots[0], slots[1] = slots[1], slots[0]
                elif change == "collection":
                    slots[0]["collection_level"] = "SR 10"
                elif change == "missing_collection":
                    slots[0].pop("collection_level")
                elif change == "character":
                    slots[0]["id"] = 226
                elif change == "team_number":
                    teams[0]["team_number"] = 3
                else:
                    teams.pop()
                self.revision.defender_teams = teams
                self.db.commit()
                self.assert_achievement(None)

    def test_explicit_result_registration_id_is_respected(self):
        registration = models.ArenaDeckRegistration(tournament_id=self.tournament.id,
            player_id=self.revision.defender_id, phase="best8", qualification="other-version",
            teams=self.revision.defender_teams)
        self.db.add(registration)
        self.db.flush()
        self.revision.defender_registration_id = registration.id
        self.db.commit()
        self.assert_achievement(None)

    def test_unversioned_match_does_not_prove_deck_identity(self):
        match = models.Match(tournament_id=self.tournament.id, stage="Best 64",
                             attacker_id=self.revision.attacker_id, defender_id=self.revision.defender_id,
                             winner_id=self.revision.winner_id)
        self.db.add(match)
        self.db.flush()
        for number, winner_id in enumerate(self.revision.rounds, 1):
            self.db.add(models.RoundResult(match_id=match.id, round_number=number, winner_id=winner_id))
        self.db.delete(self.revision)
        self.db.commit()
        self.assert_achievement(None)
