"""Exercise legacy league results through both dashboard API entry points."""
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import auth
from database import Base, SessionLocal, engine
import main
import models
from scripts import link_legacy_league
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

    def assert_achievement(self, expected, *, clear_cache=True, target=TARGET, removed=None):
        if clear_cache:
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
            cards = {team["canonical_id"]: team for team in result.json()["teams"]}
            if removed is not None:
                self.assertNotIn(removed, cards)
            card = cards[target]
            self.assertEqual((card["count"], card["total_matches"], card["win_rate"]), (1, 1, 100.0))
            self.assertEqual(card["composition_best_result"], expected)

    def test_exact_legacy_snapshot_restores_best64_for_the_winning_team(self):
        self.assertIsNone(self.revision.defender_registration_id)
        self.assert_achievement("best64")

    def correct_legacy_registration(self, player_id, replacement=None):
        teams = arena_phases.legacy_teams(self.db.get(models.Player, player_id), self.db)
        if replacement is None:
            teams[1]["characters"].reverse()
        else:
            self.db.add(models.Character(id=replacement, name="Replacement", is_arena_relevant=True))
            teams[1]["characters"][0]["id"] = replacement
        self.tournament.publication_status = "draft"
        self.db.commit()
        response = self.client.post(f"/api/tournaments/{self.tournament.id}/teams",
                                    json={"seed_number": 2, "teams": teams})
        self.assertEqual(response.status_code, 200, response.text)
        self.tournament.publication_status = "published"
        self.db.commit()

    def test_correction_links_a_saved_snapshot_of_a_legacy_registration(self):
        self.assertIsNone(self.revision.defender_registration_id)
        self.correct_legacy_registration(self.revision.defender_id)
        self.db.refresh(self.revision)
        self.assertIsNotNone(self.revision.defender_registration_id)
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

    def convert_to_legacy_match(self):
        match = models.Match(tournament_id=self.tournament.id, stage="Best 64",
                             attacker_id=self.revision.attacker_id, defender_id=self.revision.defender_id,
                             winner_id=self.revision.winner_id)
        self.db.add(match)
        self.db.flush()
        for number, winner_id in enumerate(self.revision.rounds, 1):
            self.db.add(models.RoundResult(match_id=match.id, round_number=number, winner_id=winner_id))
        self.db.delete(self.revision)
        self.db.commit()
        return match

    def test_unversioned_match_does_not_prove_deck_identity(self):
        defender_id = self.revision.defender_id
        self.convert_to_legacy_match()
        self.assert_achievement(None)
        self.correct_legacy_registration(defender_id)
        self.assertEqual(self.db.query(models.ArenaMatchRevision).count(), 0)
        self.assert_achievement(None)

    def test_legacy_link_preview_apply_rollback_and_cache(self):
        match = self.convert_to_legacy_match()
        tournament_id = self.tournament.id
        before = arena_phases.state(self.tournament, self.db)

        def invoke(action, digest=None):
            args = SimpleNamespace(action=action, digest=digest, operator="test-admin",
                                   tournament_id=tournament_id, expect_database=engine.url.database)
            with SessionLocal.begin() as db:
                return link_legacy_league.run(db, args)

        self.assert_achievement(None)
        plan = invoke("preview")
        self.assertEqual((plan["matches"], plan["player_links"], plan["skipped"]), (1, 2, []))
        self.assertIsNone(plan["active_digest"])
        self.assertEqual(plan["links"][0]["match_id"], match.id)
        self.assertEqual(plan["links"][0]["achievements"][match.defender_id], "best64")
        with self.assertRaisesRegex(ValueError, "preview changed"):
            invoke("apply", "wrong digest")
        self.assert_achievement(None, clear_cache=False)
        self.assertEqual(invoke("apply", plan["digest"])["action"], "applied")
        self.assertEqual(invoke("apply", plan["digest"])["action"], "already_applied")
        self.assert_achievement("best64", clear_cache=False)
        self.assertEqual(arena_phases.state(self.tournament, self.db), before)

        self.correct_legacy_registration(match.defender_id, replacement=226)
        corrected = "94,107,109,147,226"
        self.assert_achievement("best64", clear_cache=False, target=corrected, removed=TARGET)
        after = arena_phases.state(self.tournament, self.db)
        self.assertEqual(
            [(m["legacy_match_id"], m["revision_id"], m["winner_id"], m["rounds"], m["advancement"]) for m in before["matches"]],
            [(m["legacy_match_id"], m["revision_id"], m["winner_id"], m["rounds"], m["advancement"]) for m in after["matches"]],
        )
        self.assertEqual(self.db.query(models.ArenaMatchRevision).count(), 0)
        self.assertEqual(invoke("rollback", plan["digest"])["action"], "rolled_back")
        self.assertNotEqual(arena_phases.state(self.tournament, self.db), before)
        self.assertEqual(arena_phases.state(self.tournament, self.db), after)
