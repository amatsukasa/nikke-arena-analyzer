"""Phase 5A publication validation and published-data protection tests."""

from datetime import date
from copy import deepcopy
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DASHBOARD_CACHE_TTL_SECONDS", "60")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
from services.champion_publication import validate_champion_publication  # noqa: E402
from services.champion_snapshot import enrich_champion_snapshot_stats  # noqa: E402


class ChampionPublicationPhase5ATest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        main._dashboard_cache.clear()
        self.db = SessionLocal()
        self.owner = self._user("owner@example.invalid", "contributor")
        self.admin = self._user("admin@example.invalid", "admin")
        self.other = self._user("other@example.invalid", "contributor")
        self.tournament = models.Tournament(
            name="Champion", date=date(2026, 1, 1), registration_scope="champion_8",
            publication_status="draft", created_by=self.owner.id,
        )
        self.db.add(self.tournament)
        for character_id in range(1, 201):
            self.db.add(models.Character(id=character_id, name=f"Character {character_id}"))
        self.db.add(models.Character(id=9999, name="空枠"))
        self.db.flush()
        self.players = []
        for slot in range(1, 9):
            player = models.Player(
                tournament_id=self.tournament.id, champion_slot=slot,
                seed_number=(slot - 1) * 8 + 1,
                name=f"Player {(slot - 1) * 8 + 1}",
            )
            self.db.add(player); self.db.flush(); self.players.append(player)
            deck_set = models.DeckSet(player_id=player.id)
            self.db.add(deck_set); self.db.flush()
            base = (slot - 1) * 25
            for team_number in range(1, 6):
                first = base + (team_number - 1) * 5 + 1
                self.db.add(models.DeckTeam(
                    deck_set_id=deck_set.id, team_number=team_number,
                    char1_id=first, char2_id=first + 1, char3_id=first + 2,
                    char4_id=first + 3, char5_id=first + 4,
                ))
        self.db.commit()
        self._complete_bracket()

    def tearDown(self):
        self.db.close()
        main._dashboard_cache.clear()

    def _user(self, email, role):
        user = models.AppUser(email=email, hashed_password="x", role=role, approval_status="approved")
        self.db.add(user); self.db.flush(); return user

    @staticmethod
    def _payload(attacker, defender):
        return schemas.ChampionMatchUpsert(
            winner_id=attacker.id,
            round_results=[
                {"round_number": number, "winner_id": attacker.id if number <= 3 else defender.id}
                for number in range(1, 6)
            ],
        )

    def _save(self, stage, slot, attacker, defender):
        return main.save_champion_match(
            self.tournament.id, stage, slot, self._payload(attacker, defender),
            self.db, self.owner,
        )

    def _complete_bracket(self):
        for slot in range(1, 5):
            self._save("quarterfinal", slot, self.players[(slot - 1) * 2], self.players[(slot - 1) * 2 + 1])
        self._save("semifinal", 1, self.players[0], self.players[2])
        self._save("semifinal", 2, self.players[4], self.players[6])
        self._save("final", 1, self.players[0], self.players[4])

    def _validate(self):
        return validate_champion_publication(self.tournament, self.db)

    def _codes(self, result):
        return {error["code"] for error in result["errors"]}

    def test_complete_tournament_returns_exact_counts_and_is_publishable(self):
        result = self._validate()
        self.assertTrue(result["can_publish"], result)
        self.assertEqual(result["counts"], {
            "players": 8, "complete_players": 8, "teams": 40,
            "matches": 7, "round_results": 35,
        })
        self.assertEqual(result["invalid_slots"], [])
        self.assertEqual(result["invalid_match_slots"], [])

    def test_published_champion_dashboard_is_anonymous_and_scope_aware(self):
        self.tournament.publication_status = "published"
        self.db.commit()

        summary = main.get_dashboard_summary(self.tournament.id, self.db, None)
        self.assertEqual(
            (summary["registered_player_count"], summary["expected_player_count"],
             summary["registered_team_count"], summary["expected_team_count"],
             summary["registered_match_count"], summary["expected_match_count"]),
            (8, 8, 40, 40, 7, 7),
        )
        self.assertEqual(summary["missing_seed_numbers"], [])

        stats = main.get_dashboard_stats(self.tournament.id, None, self.db, None)
        matchups = main.get_dashboard_matchups(self.tournament.id, None, self.db, None)
        best8 = main.get_best8_decks(self.tournament.id, self.db, None)
        players = main.get_dashboard_player_stats(self.tournament.id, None, self.db, None)
        self.assertEqual((stats["total_players"], stats["total_matches"]), (8, 7))
        self.assertEqual(len(matchups["matchups"]), 35)
        self.assertEqual((len(best8), len(players["players"])), (8, 8))
        self.assertTrue(all(item["player"]["id"] for item in best8))
        self.assertTrue(all(len(item["decks"]) == 5 for item in best8))

    def test_seed_must_belong_to_the_players_champion_slot(self):
        self.players[1].seed_number = 8
        self.players[1].name = "Player 8"
        self.db.commit()
        result = self._validate()
        self.assertFalse(result["can_publish"])
        self.assertIn("seed_outside_champion_slot_range", self._codes(result))

    def test_champion_snapshot_uses_8_players_40_teams_7_matches_and_correct_results(self):
        raw = main._compute_dashboard_stats(self.tournament.id, self.db, self.owner)
        direct = deepcopy(raw)
        direct_matchups = main.get_dashboard_matchups(
            self.tournament.id, None, self.db, self.owner
        )["matchups"]
        stats = enrich_champion_snapshot_stats(raw, self.tournament.id, self.db)
        self.assertEqual((stats["total_players"], stats["total_matches"]), (8, 7))
        self.assertEqual(sum(team["count"] for team in stats["team_usage"]), 40)
        self.assertEqual(sum(character["count"] for character in stats["character_stats"]), 200)
        self.assertEqual(len(stats["matchups"]), 35)
        self.assertEqual(len({item["match_id"] for item in stats["matchups"]}), 7)
        self.assertEqual(
            [(item["match_id"], item["round_number"], item["winner_is_attacker"]) for item in stats["matchups"]],
            [(item["match_id"], item["round_number"], item["winner_is_attacker"]) for item in direct_matchups],
        )
        self.assertEqual(
            [(item["canonical_id"], item["count"], item["win_count"], item["total_matches"]) for item in stats["team_usage"]],
            [(item["canonical_id"], item["count"], item["win_count"], item["total_matches"]) for item in direct["team_usage"]],
        )
        self.assertEqual(
            [(item["id"], item["count"], item["win_count"], item["total_matches"]) for item in stats["character_stats"]],
            [(item["id"], item["count"], item["win_count"], item["total_matches"]) for item in direct["character_stats"]],
        )
        best_results = {item["id"]: item["best_result"] for item in stats["character_stats"]}
        self.assertEqual(best_results[1], "優勝")
        self.assertEqual(best_results[101], "準優勝")
        self.assertEqual(best_results[51], "ベスト4")
        self.assertEqual(best_results[26], "ベスト8")
        self.assertTrue(all(item["adoption_rate"] <= 100 for item in stats["character_stats"] + stats["team_usage"]))
        with patch.object(self.db, "commit") as commit, \
             patch.object(main, "SessionLocal") as new_session:
            snapshot = main.apply_snapshot(self.tournament.id, stats, self.db)
            commit.assert_not_called()
            new_session.assert_not_called()
        self.db.flush()
        self.assertEqual(snapshot.total_players, stats["total_players"])
        self.assertEqual(snapshot.total_matches, stats["total_matches"])
        self.assertEqual(snapshot.team_usage, stats["team_usage"])
        self.assertEqual(snapshot.char_stats, stats["character_stats"])
        self.assertEqual(snapshot.matchups, stats["matchups"])

    def test_identical_team_matchups_preserve_both_player_participations(self):
        """A canonical mirror keeps distinct attacker/defender identities and a 50% aggregate."""
        for player in self.players:
            for team in player.deck_sets[0].teams:
                first = (team.team_number - 1) * 5 + 1
                team.char1_id, team.char2_id, team.char3_id = first, first + 1, first + 2
                team.char4_id, team.char5_id = first + 3, first + 4
        self.db.commit()

        raw = main._compute_dashboard_stats(self.tournament.id, self.db, self.owner)
        raw_matchups = main.get_dashboard_matchups(
            self.tournament.id, None, self.db, self.owner
        )["matchups"]
        snapshot = enrich_champion_snapshot_stats(deepcopy(raw), self.tournament.id, self.db)

        first_team = next(item for item in snapshot["team_usage"] if item["canonical_id"] == "1,2,3,4,5")
        self.assertEqual((first_team["count"], first_team["win_count"], first_team["total_matches"]), (8, 7, 14))
        self.assertEqual(first_team["win_rate"], 50.0)

        mirrored_rounds = [
            item for item in raw_matchups
            if item["canonical_attacker"] == "1,2,3,4,5"
            and item["canonical_defender"] == "1,2,3,4,5"
        ]
        self.assertEqual(len(mirrored_rounds), 7)
        for item in mirrored_rounds:
            self.assertNotEqual(item["attacker_player_id"], item["defender_player_id"])
            self.assertNotEqual(item["attacker_team_id"], item["defender_team_id"])
            self.assertIn(item["winner_player_id"], (item["attacker_player_id"], item["defender_player_id"]))
            self.assertEqual(item["attacker_team_number"], 1)
            self.assertEqual(item["defender_team_number"], 1)

        identity = lambda item: (
            item["match_id"], item["round_number"], item["attacker_player_id"],
            item["defender_player_id"], item["attacker_team_id"], item["defender_team_id"],
            item["winner_player_id"], item["winner_is_attacker"],
        )
        self.assertEqual([identity(item) for item in snapshot["matchups"]], [identity(item) for item in raw_matchups])

    def test_identical_teams_with_empty_slot_keep_matchup_identities(self):
        for player in self.players[:2]:
            team = player.deck_sets[0].teams[0]
            team.char1_id = 9999
            team.char2_id, team.char3_id, team.char4_id, team.char5_id = 2, 3, 4, 5
        self.db.commit()

        matchups = main.get_dashboard_matchups(
            self.tournament.id, None, self.db, self.owner
        )["matchups"]
        qf1 = self.db.query(models.Match).filter_by(
            tournament_id=self.tournament.id, bracket_stage="quarterfinal", bracket_slot=1,
        ).one()
        qf1_round1 = next(item for item in matchups if item["match_id"] == qf1.id and item["round_number"] == 1)
        self.assertEqual(qf1_round1["canonical_attacker"], qf1_round1["canonical_defender"])
        self.assertIn("9999", qf1_round1["canonical_attacker"])
        self.assertNotEqual(qf1_round1["attacker_player_id"], qf1_round1["defender_player_id"])
        self.assertNotEqual(qf1_round1["attacker_team_id"], qf1_round1["defender_team_id"])

    def test_player_slot_count_extra_player_seed_name_and_deck_errors(self):
        ninth = models.Player(tournament_id=self.tournament.id, champion_slot=None, seed_number=None, name="extra")
        self.db.add(ninth); self.db.commit()
        result = self._validate()
        self.assertEqual(result["counts"]["players"], 9)
        self.assertIn("unexpected_unslotted_players", self._codes(result))
        self.db.delete(ninth); self.db.commit()
        self.db.delete(self.players[-1]); self.db.commit()
        result = self._validate()
        self.assertEqual(result["counts"]["players"], 7)
        self.assertFalse(result["can_publish"])
        self.assertIn("invalid_champion_slots", self._codes(result))
        extra = models.Player(tournament_id=self.tournament.id, champion_slot=None, seed_number=None, name="extra")
        self.db.add(extra); self.players[0].name = "wrong"; self.db.commit()
        result = self._validate()
        self.assertIn("unexpected_unslotted_players", self._codes(result))
        self.assertIn("invalid_player_name", self._codes(result))
        self.assertIn("invalid_deck_set_count", self._codes(result))

    def test_team_unknown_character_and_player_character_duplicate_are_rejected(self):
        deck_set = self.players[0].deck_sets[0]
        team = deck_set.teams[0]
        team.char1_id = 9998
        team.char2_id = team.char3_id
        team.char4_id = None
        self.db.commit()
        result = self._validate()
        self.assertIn("unknown_characters", self._codes(result))
        self.assertIn("duplicate_player_characters", self._codes(result))
        self.assertIn("unresolved_team_characters", self._codes(result))
        self.db.delete(deck_set.teams[-1]); self.db.commit()
        self.assertIn("invalid_team_numbers", self._codes(self._validate()))

    def test_repeated_empty_slots_are_publishable_and_not_character_duplicates(self):
        first_set = self.players[0].deck_sets[0]
        first_set.teams[0].char1_id = 9999
        first_set.teams[1].char1_id = 9999
        self.db.commit()
        result = self._validate()
        self.assertTrue(result["can_publish"], result["errors"])
        self.assertNotIn("duplicate_player_characters", self._codes(result))
        self.assertEqual(result["complete_player_count"], 8)
        stats = enrich_champion_snapshot_stats(
            main._compute_dashboard_stats(self.tournament.id, self.db, self.owner),
            self.tournament.id,
            self.db,
        )
        self.assertEqual(sum(team["count"] for team in stats["team_usage"]), 40)
        self.assertEqual(sum(character["count"] for character in stats["character_stats"]), 198)
        self.assertNotIn(9999, {character["id"] for character in stats["character_stats"]})

    def test_match_and_round_count_slot_and_number_errors(self):
        final = self.db.query(models.Match).filter_by(
            tournament_id=self.tournament.id, bracket_stage="final", bracket_slot=1
        ).one()
        self.db.delete(final.round_results[-1]); self.db.commit()
        result = self._validate()
        self.assertIn("invalid_round_numbers", self._codes(result))
        self.assertEqual(result["counts"]["round_results"], 34)
        self.db.add(models.RoundResult(match_id=final.id, round_number=4, winner_id=final.attacker_id))
        self.db.add(models.RoundResult(match_id=final.id, round_number=6, winner_id=final.attacker_id))
        self.db.commit()
        result = self._validate()
        self.assertEqual(result["counts"]["round_results"], 36)
        self.assertIn("invalid_round_numbers", self._codes(result))
        self.db.delete(final); self.db.commit()
        result = self._validate()
        self.assertEqual(result["counts"]["matches"], 6)
        self.assertIn("invalid_match_slots", self._codes(result))
        for index in range(2):
            self.db.add(models.Match(
                tournament_id=self.tournament.id, stage=f"extra-{index}", bracket_stage=None,
                bracket_slot=None, attacker_id=self.players[0].id,
                defender_id=self.players[1].id, winner_id=self.players[0].id,
            ))
        self.db.commit()
        self.assertEqual(self._validate()["counts"]["matches"], 8)
        self.assertIn("unexpected_matches", self._codes(self._validate()))

    def test_reversed_sides_majority_and_progression_conflicts_are_rejected(self):
        qf1 = self.db.query(models.Match).filter_by(tournament_id=self.tournament.id, bracket_stage="quarterfinal", bracket_slot=1).one()
        qf1.attacker_id, qf1.defender_id = qf1.defender_id, qf1.attacker_id
        self.db.commit()
        self.assertIn("invalid_match_participants", self._codes(self._validate()))
        qf1.attacker_id, qf1.defender_id = qf1.defender_id, qf1.attacker_id
        qf1.winner_id = qf1.defender_id
        self.db.commit()
        self.assertIn("invalid_match_winner", self._codes(self._validate()))
        qf1.winner_id = qf1.attacker_id
        sf1 = self.db.query(models.Match).filter_by(tournament_id=self.tournament.id, bracket_stage="semifinal", bracket_slot=1).one()
        sf1.attacker_id = self.players[1].id
        self.db.commit()
        self.assertIn("invalid_match_participants", self._codes(self._validate()))

    def test_readiness_and_publish_share_validator_and_failed_publish_has_no_effects(self):
        self.db.delete(self.players[0].deck_sets[0].teams[-1]); self.db.commit()
        with patch.object(main, "validate_champion_publication", wraps=validate_champion_publication) as validator:
            checked = main.get_tournament_publication(self.tournament.id, self.db, self.owner)
            self.assertFalse(checked["readiness"]["can_publish"])
            with patch.object(self.db, "commit", wraps=self.db.commit) as commit, \
                 patch.object(main, "apply_snapshot") as snapshot, \
                 patch.object(main, "invalidate_dashboard_cache") as cache:
                with self.assertRaises(HTTPException) as raised:
                    main.update_tournament_publication(
                        self.tournament.id, {"published": True}, BackgroundTasks(), self.db, self.owner
                    )
                self.assertEqual(raised.exception.status_code, 409)
                commit.assert_not_called(); snapshot.assert_not_called(); cache.assert_not_called()
            self.assertGreaterEqual(validator.call_count, 2)
        self.assertEqual(self.tournament.publication_status, "draft")
        self.assertEqual(self.db.query(models.TournamentSnapshot).count(), 0)

    def test_publish_snapshot_and_status_are_one_commit_and_failure_rolls_back(self):
        stats = {"team_usage": [], "character_stats": [], "matchups": [], "total_players": 8, "total_matches": 7}
        with patch.object(main, "_compute_dashboard_stats", return_value=stats), \
             patch.object(main, "SessionLocal") as new_session, \
             patch.object(self.db, "commit", wraps=self.db.commit) as commit:
            response = main.update_tournament_publication(
                self.tournament.id, {"published": True}, BackgroundTasks(), self.db, self.owner
            )
            new_session.assert_not_called()
        self.assertEqual(response["publication_status"], "published")
        self.assertEqual(commit.call_count, 1)
        self.assertEqual(self.db.query(models.TournamentSnapshot).one().total_players, 8)

        main.update_tournament_publication(
            self.tournament.id, {"published": False}, BackgroundTasks(), self.db, self.owner
        )
        self.assertEqual(self.tournament.publication_status, "draft")
        self.assertEqual(self.db.query(models.TournamentSnapshot).count(), 0)
        with patch.object(main, "_compute_dashboard_stats", side_effect=RuntimeError("snapshot failed")):
            with self.assertRaises(RuntimeError):
                main.update_tournament_publication(
                    self.tournament.id, {"published": True}, BackgroundTasks(), self.db, self.owner
                )
        self.db.refresh(self.tournament)
        self.assertEqual(self.tournament.publication_status, "draft")
        with patch.object(main, "_compute_dashboard_stats", return_value=stats), \
             patch.object(self.db, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaises(RuntimeError):
                main.update_tournament_publication(
                    self.tournament.id, {"published": True}, BackgroundTasks(), self.db, self.owner
                )
        self.db.refresh(self.tournament)
        self.assertEqual(self.tournament.publication_status, "draft")
        self.assertEqual(self.db.query(models.TournamentSnapshot).count(), 0)

    def test_published_mutations_are_blocked_but_get_icon_and_analysis_routes_are_not(self):
        self.tournament.publication_status = "published"; self.db.commit()
        operations = [
            (main.upsert_champion_slot, (self.tournament.id, 1, schemas.ChampionSlotUpsert(seed_number=1), self.db, self.owner)),
            (main.save_champion_teams, (self.tournament.id, self.players[0].id, schemas.ChampionTeamsUpsert(teams=[]), self.db, self.owner)),
            (main.save_champion_match, (self.tournament.id, "quarterfinal", 1, self._payload(self.players[0], self.players[1]), self.db, self.owner)),
        ]
        for function, args in operations:
            with self.assertRaises(HTTPException) as raised:
                function(*args)
            self.assertEqual(raised.exception.status_code, 409)
        self.assertIsNotNone(main.get_champion_player_by_id(self.tournament.id, self.players[0].id, self.db, None))
        route_paths = {route.path for route in main.app.routes}
        self.assertIn("/api/tournaments/{tournament_id}/players/by-id/{player_id}/icon", route_paths)
        self.assertIn("/api/tournaments/{tournament_id}/matches/{bracket_stage}/{bracket_slot}/analyze", route_paths)
        main.update_tournament_publication(self.tournament.id, {"published": False}, BackgroundTasks(), self.db, self.owner)
        main.upsert_champion_slot(self.tournament.id, 1, schemas.ChampionSlotUpsert(seed_number=1), self.db, self.owner)

    def test_locked_query_reloads_latest_status_before_edit_decision(self):
        latest = MagicMock(
            id=self.tournament.id, registration_scope="champion_8",
            publication_status="published", created_by=self.owner.id,
        )
        query = MagicMock()
        query.filter.return_value = query
        query.populate_existing.return_value = query
        query.with_for_update.return_value = query
        query.first.return_value = latest
        fake_db = MagicMock()
        fake_db.query.return_value = query
        locked = main.require_locked_champion_tournament_manager(
            self.tournament.id, fake_db, self.owner
        )
        query.populate_existing.assert_called_once_with()
        query.with_for_update.assert_called_once_with()
        self.assertIs(locked, latest)
        with self.assertRaises(HTTPException) as raised:
            main.require_unpublished_champion_edit(locked)
        self.assertEqual(raised.exception.status_code, 409)

    def test_postgresql_publish_lock_makes_waiting_editor_recheck_published(self):
        if engine.dialect.name != "postgresql":
            self.skipTest("requires disposable PostgreSQL")
        locker = SessionLocal()
        locked_tournament = main.require_locked_champion_tournament_manager(
            self.tournament.id, locker, locker.get(models.AppUser, self.owner.id)
        )
        started = threading.Event()
        finished = threading.Event()
        outcome = []

        def edit_slot():
            session = SessionLocal()
            try:
                started.set()
                main.upsert_champion_slot(
                    self.tournament.id, 1, schemas.ChampionSlotUpsert(seed_number=1),
                    session, session.get(models.AppUser, self.owner.id),
                )
                outcome.append("updated")
            except HTTPException as exc:
                outcome.append(exc.status_code)
            finally:
                session.close(); finished.set()

        thread = threading.Thread(target=edit_slot)
        thread.start(); started.wait(2); time.sleep(0.25)
        self.assertFalse(finished.is_set())
        locked_tournament.publication_status = "published"
        locker.commit(); thread.join(3); locker.close()
        self.assertEqual(outcome, [409])

    def test_postgresql_editor_lock_makes_publisher_validate_committed_edit(self):
        if engine.dialect.name != "postgresql":
            self.skipTest("requires disposable PostgreSQL")
        editor = SessionLocal()
        main.require_locked_champion_tournament_manager(
            self.tournament.id, editor, editor.get(models.AppUser, self.owner.id)
        )
        team = editor.query(models.DeckTeam).join(models.DeckSet).filter(
            models.DeckSet.player_id == self.players[0].id
        ).first()
        editor.delete(team)
        started = threading.Event()
        finished = threading.Event()
        outcome = []

        def publish():
            session = SessionLocal()
            try:
                started.set()
                main.update_tournament_publication(
                    self.tournament.id, {"published": True}, BackgroundTasks(),
                    session, session.get(models.AppUser, self.owner.id),
                )
                outcome.append("published")
            except HTTPException as exc:
                outcome.append(exc.status_code)
            finally:
                session.close(); finished.set()

        thread = threading.Thread(target=publish)
        thread.start(); started.wait(2); time.sleep(0.25)
        self.assertFalse(finished.is_set())
        editor.commit(); thread.join(3); editor.close()
        self.assertEqual(outcome, [409])
        verify = SessionLocal()
        self.assertEqual(verify.get(models.Tournament, self.tournament.id).publication_status, "draft")
        self.assertEqual(verify.query(models.TournamentSnapshot).count(), 0)
        verify.close()

    def test_owner_admin_other_not_found_and_full64_behavior(self):
        self.assertTrue(main.get_tournament_publication(self.tournament.id, self.db, self.owner))
        self.assertTrue(main.get_tournament_publication(self.tournament.id, self.db, self.admin))
        with self.assertRaises(HTTPException) as raised:
            main.get_tournament_publication(self.tournament.id, self.db, self.other)
        self.assertEqual(raised.exception.status_code, 403)
        with self.assertRaises(HTTPException) as raised:
            main.get_tournament_publication(self.tournament.id, self.db, None)
        self.assertEqual(raised.exception.status_code, 401)
        with self.assertRaises(HTTPException) as raised:
            main.get_tournament_publication(999999, self.db, self.owner)
        self.assertEqual(raised.exception.status_code, 404)
        full = models.Tournament(name="Full", date=date(2026, 1, 1), registration_scope="full_64", created_by=self.owner.id)
        self.db.add(full); self.db.flush()
        player = models.Player(tournament_id=full.id, seed_number=1, name="Player 1")
        self.db.add(player); self.db.flush(); deck = models.DeckSet(player_id=player.id); self.db.add(deck); self.db.flush()
        for number in range(1, 6):
            self.db.add(models.DeckTeam(deck_set_id=deck.id, team_number=number, char1_id=1, char2_id=2, char3_id=3, char4_id=4, char5_id=5))
        self.db.commit()
        readiness = main.get_publication_readiness(full, self.db)
        self.assertTrue(readiness["can_publish"])
        self.assertNotIn("errors", readiness)


if __name__ == "__main__":
    unittest.main()
