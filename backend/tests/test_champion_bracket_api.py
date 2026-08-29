"""Phase 4A tests for the structured champion-eight bracket API."""

from datetime import date
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

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
from services.champion_bracket import CHAMPION_BRACKET, dependent_keys, participant_ids  # noqa: E402


class ChampionBracketApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        main._dashboard_cache.clear()
        self.db = SessionLocal()
        self.owner = self._user("bracket-owner@example.invalid", "contributor")
        self.admin = self._user("bracket-admin@example.invalid", "admin")
        self.other = self._user("bracket-other@example.invalid", "contributor")
        self.tournament = self._tournament("champion", "champion_8", self.owner)
        self.full = self._tournament("full", "full_64", self.owner)
        self.players = [self._player(self.tournament, slot) for slot in range(1, 9)]
        for player in self.players:
            self._complete_deck(player)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        main._dashboard_cache.clear()

    def _user(self, email, role):
        user = models.AppUser(email=email, hashed_password="unused", role=role, approval_status="approved")
        self.db.add(user); self.db.flush()
        return user

    def _tournament(self, name, scope, owner, published=False):
        tournament = models.Tournament(
            name=name, date=date(2026, 1, 1), registration_scope=scope,
            created_by=owner.id, publication_status="published" if published else "draft",
        )
        self.db.add(tournament); self.db.flush()
        return tournament

    def _player(self, tournament, slot):
        player = models.Player(
            tournament_id=tournament.id, champion_slot=slot,
            seed_number=slot, name=f"Player {slot}",
        )
        self.db.add(player); self.db.flush()
        return player

    def _complete_deck(self, player):
        deck_set = models.DeckSet(player_id=player.id)
        self.db.add(deck_set); self.db.flush()
        for team_number in range(1, 6):
            first = (team_number - 1) * 5 + 1
            self.db.add(models.DeckTeam(
                deck_set_id=deck_set.id, team_number=team_number,
                char1_id=first, char2_id=first + 1, char3_id=first + 2,
                char4_id=first + 3, char5_id=first + 4,
            ))

    @staticmethod
    def _payload(attacker, defender, attacker_wins=3):
        winners = [attacker] * attacker_wins + [defender] * (5 - attacker_wins)
        return schemas.ChampionMatchUpsert(
            winner_id=attacker if attacker_wins >= 3 else defender,
            round_results=[
                {"round_number": number, "winner_id": winner}
                for number, winner in enumerate(winners, start=1)
            ],
        )

    def _save(self, stage, slot, attacker, defender, attacker_wins=3, user=None):
        return main.save_champion_match(
            self.tournament.id, stage, slot,
            self._payload(attacker.id, defender.id, attacker_wins),
            self.db, user or self.owner,
        )

    def _complete_bracket(self):
        self._save("quarterfinal", 1, self.players[0], self.players[1], 3)
        self._save("quarterfinal", 2, self.players[2], self.players[3], 3)
        self._save("quarterfinal", 3, self.players[4], self.players[5], 3)
        self._save("quarterfinal", 4, self.players[6], self.players[7], 3)
        self._save("semifinal", 1, self.players[0], self.players[2], 3)
        self._save("semifinal", 2, self.players[4], self.players[6], 3)
        self._save("final", 1, self.players[0], self.players[4], 3)

    def _match(self, stage, slot):
        return self.db.query(models.Match).filter_by(
            tournament_id=self.tournament.id,
            bracket_stage=stage,
            bracket_slot=slot,
        ).first()

    def _assert_status(self, status, function, *args):
        with self.assertRaises(HTTPException) as raised:
            function(*args)
        self.assertEqual(raised.exception.status_code, status)

    def test_pure_fixed_structure_order_sides_upstreams_and_dependencies(self):
        self.assertEqual([item.name for item in CHAMPION_BRACKET], ["QF1", "QF2", "QF3", "QF4", "SF1", "SF2", "Final"])
        slot_ids = {slot: slot * 10 for slot in range(1, 9)}
        winners = {
            ("quarterfinal", 1): 10, ("quarterfinal", 2): 30,
            ("quarterfinal", 3): 50, ("quarterfinal", 4): 70,
            ("semifinal", 1): 10, ("semifinal", 2): 50,
        }
        expected = [(10, 20), (30, 40), (50, 60), (70, 80), (10, 30), (50, 70), (10, 50)]
        self.assertEqual([participant_ids(item, slot_ids, winners) for item in CHAMPION_BRACKET], expected)
        self.assertEqual(dependent_keys(("quarterfinal", 1)), (("semifinal", 1),))
        self.assertEqual(dependent_keys(("quarterfinal", 3)), (("semifinal", 2),))

    def test_state_locked_ready_complete_and_progression(self):
        initial = schemas.ChampionBracketResponse.model_validate(
            main.get_champion_bracket(self.tournament.id, self.db, self.owner)
        )
        self.assertEqual([match.status for match in initial.matches], ["ready"] * 4 + ["locked"] * 3)
        saved = schemas.ChampionBracketMatchResponse.model_validate(
            self._save("quarterfinal", 1, self.players[0], self.players[1])
        )
        self.assertEqual(saved.status, "complete")
        self._save("quarterfinal", 2, self.players[2], self.players[3])
        progressed = schemas.ChampionBracketResponse.model_validate(
            main.get_champion_bracket(self.tournament.id, self.db, self.owner)
        )
        self.assertEqual(progressed.matches[4].status, "ready")
        self.assertEqual(progressed.matches[4].attacker.id, self.players[0].id)
        self.assertEqual(progressed.matches[4].defender.id, self.players[2].id)

    def test_missing_player_and_incomplete_deck_are_locked(self):
        missing = self._tournament("missing", "champion_8", self.owner)
        p1 = self._player(missing, 1); self._complete_deck(p1)
        p2 = self._player(missing, 2)
        self.db.commit()
        response = schemas.ChampionBracketResponse.model_validate(
            main.get_champion_bracket(missing.id, self.db, self.owner)
        )
        self.assertEqual(response.matches[0].status, "locked")
        self.assertIsNotNone(response.matches[0].attacker)
        self.assertIsNotNone(response.matches[0].defender)

    def test_all_six_majority_patterns_and_match_id_idempotency(self):
        match_id = None
        for attacker_wins in (5, 4, 3, 2, 1, 0):
            with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
                response = schemas.ChampionBracketMatchResponse.model_validate(
                    self._save("quarterfinal", 1, self.players[0], self.players[1], attacker_wins)
                )
            match_id = match_id or response.match_id
            self.assertEqual(response.match_id, match_id)
            self.assertEqual(len(response.round_results), 5)
            commit.assert_called_once_with()
        self.assertEqual(self.db.query(models.Match).count(), 1)
        self.assertEqual(self.db.query(models.RoundResult).count(), 5)

    def test_save_qf_sf_final_fixed_attacker_defender(self):
        self._complete_bracket()
        expected = {
            ("quarterfinal", 1): (1, 2), ("quarterfinal", 2): (3, 4),
            ("quarterfinal", 3): (5, 6), ("quarterfinal", 4): (7, 8),
            ("semifinal", 1): (1, 3), ("semifinal", 2): (5, 7),
            ("final", 1): (1, 5),
        }
        for key, slots in expected.items():
            match = self._match(*key)
            self.assertEqual((match.attacker.champion_slot, match.defender.champion_slot), slots)
            self.assertTrue(main.champion_match_is_complete(match, (match.attacker_id, match.defender_id)))

    def test_round_validation_and_extra_participant_fields(self):
        valid = self._payload(self.players[0].id, self.players[1].id)
        variants = []
        for rounds in (valid.round_results[:4], valid.round_results + [valid.round_results[0]]):
            variants.append(schemas.ChampionMatchUpsert(winner_id=valid.winner_id, round_results=rounds))
        duplicate = valid.model_dump(); duplicate["round_results"][4]["round_number"] = 4; variants.append(schemas.ChampionMatchUpsert.model_validate(duplicate))
        outside = valid.model_dump(); outside["round_results"][4]["round_number"] = 6; variants.append(schemas.ChampionMatchUpsert.model_validate(outside))
        stranger = valid.model_dump(); stranger["round_results"][0]["winner_id"] = 999; variants.append(schemas.ChampionMatchUpsert.model_validate(stranger))
        mismatch = valid.model_copy(update={"winner_id": self.players[1].id}); variants.append(mismatch)
        for payload in variants:
            self._assert_status(422, main.save_champion_match, self.tournament.id, "quarterfinal", 1, payload, self.db, self.owner)
        with self.assertRaises(ValidationError):
            schemas.ChampionMatchUpsert.model_validate({**valid.model_dump(), "attacker_id": self.players[0].id})
        self.assertEqual(self.db.query(models.Match).count(), 0)

    def test_invalid_slot_upstream_decks_scope_and_permissions(self):
        payload = self._payload(self.players[0].id, self.players[1].id)
        self._assert_status(422, main.save_champion_match, self.tournament.id, "group", 1, payload, self.db, self.owner)
        self._assert_status(422, main.save_champion_match, self.tournament.id, "quarterfinal", 5, payload, self.db, self.owner)
        self._assert_status(409, main.save_champion_match, self.tournament.id, "semifinal", 1, payload, self.db, self.owner)
        deck = self.players[0].deck_sets[0]; self.db.delete(deck); self.db.commit()
        self._assert_status(409, main.save_champion_match, self.tournament.id, "quarterfinal", 1, payload, self.db, self.owner)
        self._assert_status(409, main.get_champion_bracket, self.full.id, self.db, self.owner)
        self._assert_status(403, main.save_champion_match, self.tournament.id, "quarterfinal", 1, payload, self.db, self.other)
        self._assert_status(401, main.save_champion_match, self.tournament.id, "quarterfinal", 1, payload, self.db, None)
        self._assert_status(404, main.save_champion_match, 999999, "quarterfinal", 1, payload, self.db, self.owner)

    def test_bracket_view_permissions_public_and_private(self):
        self._assert_status(401, main.get_champion_bracket, self.tournament.id, self.db, None)
        self._assert_status(403, main.get_champion_bracket, self.tournament.id, self.db, self.other)
        self.tournament.publication_status = "published"; self.db.commit()
        response = main.get_champion_bracket(self.tournament.id, self.db, None)
        self.assertEqual(len(response["matches"]), 7)

    def test_qf1_change_deletes_sf1_final_only_and_qf3_change_deletes_sf2_final_only(self):
        self._complete_bracket()
        self._save("quarterfinal", 1, self.players[0], self.players[1], 2)
        self.assertIsNone(self._match("semifinal", 1)); self.assertIsNone(self._match("final", 1))
        self.assertIsNotNone(self._match("semifinal", 2))
        self._save("semifinal", 1, self.players[1], self.players[2], 3)
        self._save("final", 1, self.players[1], self.players[4], 3)
        self._save("quarterfinal", 3, self.players[4], self.players[5], 2)
        self.assertIsNone(self._match("semifinal", 2)); self.assertIsNone(self._match("final", 1))
        self.assertIsNotNone(self._match("semifinal", 1))

    def test_sf1_change_deletes_final_and_unrelated_matches_remain(self):
        self._complete_bracket()
        self._save("semifinal", 1, self.players[0], self.players[2], 2)
        self.assertIsNone(self._match("final", 1))
        self.assertIsNotNone(self._match("semifinal", 2))
        self.assertIsNotNone(self._match("quarterfinal", 4))

    def test_final_resave_keeps_other_six_matches(self):
        self._complete_bracket()
        existing_ids = {
            (match.bracket_stage, match.bracket_slot): match.id
            for match in self.db.query(models.Match).all()
        }
        self._save("final", 1, self.players[0], self.players[4], 2)
        current = {
            (match.bracket_stage, match.bracket_slot): match.id
            for match in self.db.query(models.Match).all()
        }
        self.assertEqual(current, existing_ids)

    def test_same_winner_preserves_valid_downstream_but_deletes_inconsistent_downstream(self):
        self._complete_bracket()
        sf1_id = self._match("semifinal", 1).id; final_id = self._match("final", 1).id
        self._save("quarterfinal", 1, self.players[0], self.players[1], 4)
        self.assertEqual(self._match("semifinal", 1).id, sf1_id)
        self.assertEqual(self._match("final", 1).id, final_id)
        sf1 = self._match("semifinal", 1)
        sf1.attacker_id, sf1.defender_id = sf1.defender_id, sf1.attacker_id
        self.db.commit()
        self._save("quarterfinal", 1, self.players[0], self.players[1], 5)
        self.assertIsNone(self._match("semifinal", 1))
        self.assertIsNone(self._match("final", 1))
        self.assertIsNotNone(self._match("semifinal", 2))

    def test_commit_failure_restores_upstream_rounds_and_all_downstream(self):
        self._complete_bracket()
        qf1 = self._match("quarterfinal", 1)
        old_winner = qf1.winner_id
        old_rounds = [(result.round_number, result.winner_id) for result in qf1.round_results]
        with patch.object(self.db, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaises(RuntimeError):
                self._save("quarterfinal", 1, self.players[0], self.players[1], 2)
        self.db.refresh(qf1)
        self.assertEqual(qf1.winner_id, old_winner)
        self.assertEqual([(result.round_number, result.winner_id) for result in qf1.round_results], old_rounds)
        self.assertIsNotNone(self._match("semifinal", 1)); self.assertIsNotNone(self._match("final", 1))

    def test_cache_boundary_and_route_registration(self):
        key = main._dashboard_cache_key(self.tournament.id, "stats")
        main._dashboard_cache[key] = {"value": {}, "expires_at": float("inf")}
        self._save("quarterfinal", 1, self.players[0], self.players[1])
        self.assertNotIn(key, main._dashboard_cache)
        with patch.object(main, "invalidate_dashboard_cache", side_effect=RuntimeError("cache failed")), patch("builtins.print") as log:
            response = self._save("quarterfinal", 1, self.players[0], self.players[1], 4)
        self.assertEqual(response["status"], "complete")
        self.assertIn(f"tournament={self.tournament.id}", log.call_args.args[0])
        expected = {
            ("GET", "/api/tournaments/{tournament_id}/champion-bracket", main.get_champion_bracket),
            ("PUT", "/api/tournaments/{tournament_id}/matches/{bracket_stage}/{bracket_slot}", main.save_champion_match),
            ("POST", "/api/tournaments/{tournament_id}/matches", main.save_match),
        }
        routes = {(method, route.path, route.endpoint) for route in main.app.routes for method in (getattr(route, "methods", None) or set())}
        self.assertTrue(expected <= routes)


if __name__ == "__main__":
    unittest.main()
