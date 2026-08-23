"""Regression coverage for the existing 64-player tournament behavior.

The suite deliberately uses an isolated in-memory SQLite database.  It records
the behavior that exists before champion-eight registration is introduced; it
does not define the future eight-player rules.
"""

from collections import Counter
from datetime import date
import os
from pathlib import Path
import sys
import unittest


os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DASHBOARD_CACHE_TTL_SECONDS"] = "60"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# test_empty_slot_init installs intentionally tiny stand-in modules at import
# time.  unittest discovery imports that file before this one, so discard only
# those incomplete stand-ins and load the real application modules here.
if "database" in sys.modules and not hasattr(sys.modules["database"], "Base"):
    for module_name in ("main", "schemas", "models", "database"):
        sys.modules.pop(module_name, None)

from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402

# Let the existing registration-email test install its own resend stand-in
# during discovery.  Importing main above loads that optional integration, but
# this regression suite never calls it.
sys.modules.pop("services.registration_email", None)
sys.modules.pop("resend", None)


EXPECTED_RESULT_BY_SEED = {
    **{seed: "ベスト64" for seed in range(2, 65, 2)},
    **{seed: "ベスト32" for seed in range(3, 65, 4)},
    **{seed: "ベスト16" for seed in range(5, 65, 8)},
    9: "ベスト8",
    25: "ベスト8",
    41: "ベスト8",
    57: "ベスト8",
    17: "ベスト4",
    49: "ベスト4",
    33: "準優勝",
    1: "優勝",
}


def _match_pairs():
    """Return the current bracket's 63 matches with the left/lower seed winning."""
    pairs = []
    group_winners = []
    for group_index in range(8):
        base = group_index * 8
        first_round = [
            (base + 1, base + 2),
            (base + 3, base + 4),
            (base + 5, base + 6),
            (base + 7, base + 8),
        ]
        pairs.extend(("Best 64", left, right) for left, right in first_round)
        pairs.extend(("Best 32", left, right) for left, right in (
            (base + 1, base + 3),
            (base + 5, base + 7),
        ))
        pairs.append(("Best 16", base + 1, base + 5))
        group_winners.append(base + 1)

    quarterfinal_winners = [1, 17, 33, 49]
    pairs.extend(("Best 8", group_winners[index], group_winners[index + 1]) for index in range(0, 8, 2))
    pairs.extend(("Best 4", left, right) for left, right in ((1, 17), (33, 49)))
    pairs.append(("Final", quarterfinal_winners[0], quarterfinal_winners[2]))
    return pairs


class Full64RegressionTest(unittest.TestCase):
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
        self.user = models.AppUser(
            email="full64-regression@example.invalid",
            hashed_password="not-a-real-password",
            role="admin",
            approval_status="approved",
        )
        self.db.add(self.user)
        self.db.flush()
        self.tournament = models.Tournament(
            name="64-player regression fixture",
            date=date(2026, 1, 1),
            created_by=self.user.id,
            publication_status="published",
        )
        self.db.add(self.tournament)
        self.db.flush()
        self.players = self._create_complete_64_player_tournament()

    def tearDown(self):
        self.db.close()
        main._dashboard_cache.clear()

    def _create_complete_64_player_tournament(self):
        characters = [
            models.Character(id=index, name=f"Regression Character {index}", rarity="SSR")
            for index in range(1, 26)
        ]
        self.db.add_all(characters)
        self.db.flush()

        players = {}
        for seed in range(1, 65):
            player = models.Player(
                tournament_id=self.tournament.id,
                seed_number=seed,
                name=f"Player {seed}",
            )
            self.db.add(player)
            self.db.flush()
            players[seed] = player
            deck_set = models.DeckSet(player_id=player.id)
            self.db.add(deck_set)
            self.db.flush()
            for team_number in range(1, 6):
                first_character = (team_number - 1) * 5 + 1
                character_ids = list(range(first_character, first_character + 5))
                self.db.add(models.DeckTeam(
                    deck_set_id=deck_set.id,
                    team_number=team_number,
                    char1_id=character_ids[0],
                    char2_id=character_ids[1],
                    char3_id=character_ids[2],
                    char4_id=character_ids[3],
                    char5_id=character_ids[4],
                ))

        # Existing 64-player data does not require five RoundResults per Match.
        # One deterministic round is enough to exercise current aggregation.
        for stage, attacker_seed, defender_seed in _match_pairs():
            match = models.Match(
                tournament_id=self.tournament.id,
                stage=stage,
                attacker_id=players[attacker_seed].id,
                defender_id=players[defender_seed].id,
                winner_id=players[attacker_seed].id,
            )
            self.db.add(match)
            self.db.flush()
            self.db.add(models.RoundResult(
                match_id=match.id,
                round_number=1,
                winner_id=players[attacker_seed].id,
            ))
        self.db.commit()
        return players

    def _result_distribution_from_team_stats(self, stats):
        team = next(item for item in stats["team_usage"] if item["canonical_id"] == "1,2,3,4,5")
        return Counter(player["result"] for player in team["adopted_players"])

    def test_fixture_matches_current_save_path_structural_contract(self):
        """Guard against a direct-to-DB fixture that current registration cannot represent."""
        players = self.db.query(models.Player).filter_by(tournament_id=self.tournament.id).all()
        self.assertEqual(len(players), 64)
        self.assertEqual(sorted(player.seed_number for player in players), list(range(1, 65)))

        for player in players:
            deck_sets = self.db.query(models.DeckSet).filter_by(player_id=player.id).all()
            self.assertEqual(len(deck_sets), 1)
            teams = self.db.query(models.DeckTeam).filter_by(deck_set_id=deck_sets[0].id).all()
            self.assertEqual(sorted(team.team_number for team in teams), [1, 2, 3, 4, 5])

            player_character_ids = []
            for team in teams:
                character_ids = [
                    team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id,
                ]
                self.assertEqual(len(character_ids), 5)
                self.assertNotIn(None, character_ids)
                self.assertEqual(len(set(character_ids)), 5)
                player_character_ids.extend(character_ids)
            self.assertEqual(len(player_character_ids), 25)
            self.assertEqual(len(set(player_character_ids)), 25)

        matches = self.db.query(models.Match).filter_by(tournament_id=self.tournament.id).order_by(models.Match.id).all()
        self.assertEqual(len(matches), 63)
        self.assertEqual(
            [(match.stage, match.attacker.seed_number, match.defender.seed_number, match.winner.seed_number) for match in matches],
            [(*pair, pair[1]) for pair in _match_pairs()],
        )

    def test_existing_seed_layout_progression_side_order_and_champion(self):
        self.assertEqual(len(_match_pairs()), 63)
        bracket = main.get_tournament_bracket(self.tournament.id, self.db, None)

        self.assertEqual(len(bracket["groups"]), 8)
        for group_index, group in enumerate(bracket["groups"]):
            base = group_index * 8
            self.assertEqual([player["seed"] for player in group["players"]], list(range(base + 1, base + 9)))
            self.assertEqual(group["qf_winners"], [self.players[base + seed].id for seed in (1, 3, 5, 7)])
            self.assertEqual(group["sf_winners"], [self.players[base + 1].id, self.players[base + 5].id])
            self.assertEqual(group["winner"], self.players[base + 1].id)

        champion = bracket["champion_finals"]
        self.assertEqual([player["original_seed"] for player in champion["players"]], [1, 9, 17, 25, 33, 41, 49, 57])
        self.assertEqual(champion["qf_winners"], [self.players[seed].id for seed in (1, 17, 33, 49)])
        self.assertEqual(champion["sf_winners"], [self.players[1].id, self.players[33].id])
        self.assertEqual(champion["winner"], self.players[1].id)

        stored_pairs = [
            (match.stage, match.attacker.seed_number, match.defender.seed_number, match.winner.seed_number)
            for match in self.db.query(models.Match).order_by(models.Match.id)
        ]
        self.assertEqual(stored_pairs, [(*pair, pair[1]) for pair in _match_pairs()])

    def test_full64_identical_team_matchups_keep_both_participant_identities(self):
        stats = main._compute_dashboard_stats(self.tournament.id, self.db, self.user)
        team = next(item for item in stats["team_usage"] if item["canonical_id"] == "1,2,3,4,5")
        self.assertEqual((team["win_count"], team["total_matches"], team["win_rate"]), (63, 126, 50.0))

        matchups = main.get_dashboard_matchups(
            self.tournament.id, None, self.db, self.user
        )["matchups"]
        self.assertEqual(len(matchups), 63)
        for item in matchups:
            self.assertEqual(item["canonical_attacker"], item["canonical_defender"])
            self.assertNotEqual(item["attacker_player_id"], item["defender_player_id"])
            self.assertNotEqual(item["attacker_team_id"], item["defender_team_id"])
            self.assertEqual(item["winner_player_id"], item["attacker_player_id"])
            self.assertTrue(item["winner_is_attacker"])

    def test_all_current_result_calculations_agree_on_fixed_outcomes(self):
        expected_distribution = Counter({
            "ベスト64": 32,
            "ベスト32": 16,
            "ベスト16": 8,
            "ベスト8": 4,
            "ベスト4": 2,
            "準優勝": 1,
            "優勝": 1,
        })

        dashboard = main._compute_dashboard_stats(self.tournament.id, self.db, None)
        self.assertEqual(self._result_distribution_from_team_stats(dashboard), expected_distribution)

        by_result = main._compute_character_usage_by_result([self.tournament.id], self.db)
        self.assertEqual(
            {key: value["denominator"] for key, value in by_result.items()},
            {"all": 64, "best16": 16, "best8": 8, "best4": 4, "runner_up": 2, "champion": 1},
        )
        for key, denominator in (("all", 64), ("best16", 16), ("best8", 8), ("best4", 4), ("runner_up", 2), ("champion", 1)):
            character = next(row for row in by_result[key]["characters"] if row["character_id"] == 1)
            self.assertEqual(character["count"], denominator)
            self.assertEqual(character["usage_rate"], 100.0)

        best8 = main.get_best8_decks(self.tournament.id, self.db, self.user)
        self.assertEqual(
            [(row["player"]["original_seed"], row["result"], len(row["decks"])) for row in best8],
            [(1, "優勝", 5), (33, "準優勝", 5), (17, "ベスト4", 5), (49, "ベスト4", 5),
             (9, "ベスト8", 5), (25, "ベスト8", 5), (41, "ベスト8", 5), (57, "ベスト8", 5)],
        )

    def test_dashboard_counts_usage_player_stats_and_fixed_64_summary(self):
        summary = main.get_dashboard_summary_data(self.tournament, self.db)
        self.assertEqual(summary["registered_player_count"], 64)
        self.assertEqual(summary["expected_player_count"], 64)
        self.assertEqual(summary["registered_match_count"], 63)
        self.assertEqual(summary["expected_match_count"], 63)
        self.assertEqual(summary["registered_team_count"], 320)
        self.assertEqual(summary["expected_team_count"], 320)
        self.assertEqual(summary["missing_seed_numbers"], [])
        self.assertEqual(summary["players_without_decks"], [])
        self.assertEqual(summary["players_with_incomplete_decks"], [])

        stats = main._compute_dashboard_stats(self.tournament.id, self.db, None)
        self.assertEqual((stats["total_players"], stats["total_matches"]), (64, 63))
        self.assertEqual(len(stats["character_stats"]), 25)
        self.assertTrue(all(character["count"] == 64 for character in stats["character_stats"]))
        character_one = next(character for character in stats["character_stats"] if character["id"] == 1)
        self.assertEqual((character_one["win_count"], character_one["total_matches"], character_one["win_rate"]), (63, 126, 50.0))
        self.assertEqual(len(stats["team_usage"]), 5)
        team_one = next(team for team in stats["team_usage"] if team["canonical_id"] == "1,2,3,4,5")
        self.assertEqual((team_one["count"], team_one["win_count"], team_one["total_matches"], team_one["win_rate"]), (64, 63, 126, 50.0))

        player_stats = main.get_dashboard_player_stats(self.tournament.id, None, self.db, self.user)
        self.assertEqual([player.seed_number for player in player_stats["players"]], list(range(1, 65)))

    def test_current_publication_readiness_does_not_require_64_players_or_matches(self):
        full_readiness = main.get_publication_readiness(self.tournament, self.db)
        self.assertEqual(full_readiness, {
            "player_count": 64,
            "complete_player_count": 64,
            "incomplete_player_count": 0,
            "unresolved_slot_count": 0,
            "match_count": 63,
            "can_publish": True,
            "warnings": [],
        })

        small_tournament = models.Tournament(
            name="Current publication edge case",
            date=date(2026, 1, 2),
            created_by=self.user.id,
            publication_status="draft",
        )
        self.db.add(small_tournament)
        self.db.flush()
        player = models.Player(tournament_id=small_tournament.id, seed_number=1, name="Only Player")
        self.db.add(player)
        self.db.flush()
        deck_set = models.DeckSet(player_id=player.id)
        self.db.add(deck_set)
        self.db.flush()
        for team_number in range(1, 6):
            self.db.add(models.DeckTeam(
                deck_set_id=deck_set.id,
                team_number=team_number,
                char1_id=1, char2_id=2, char3_id=3, char4_id=4, char5_id=5,
            ))
        self.db.commit()

        readiness = main.get_publication_readiness(small_tournament, self.db)
        self.assertTrue(readiness["can_publish"])
        self.assertEqual((readiness["player_count"], readiness["match_count"]), (1, 0))
        self.assertEqual(len(readiness["warnings"]), 2)

    def test_snapshot_cross_stats_and_private_cache_keep_major_results_stable(self):
        direct = main._compute_dashboard_stats(self.tournament.id, self.db, None)
        second = main._compute_dashboard_stats(self.tournament.id, self.db, None)
        for key in ("total_players", "total_matches", "character_stats", "team_usage", "character_usage_by_result"):
            self.assertEqual(direct[key], second[key])

        main.save_snapshot(self.tournament.id, direct, self.db)
        snapshot_cross = main.get_cross_tournament_stats(main.CrossTournamentRequest(tournament_ids=[self.tournament.id]), self.db)
        self.assertEqual((snapshot_cross["total_players"], snapshot_cross["total_matches"]), (64, 63))
        self.assertEqual(direct["character_usage_by_result"], snapshot_cross["character_usage_by_result"])
        self.assertEqual(
            [(row["id"], row["count"], row["win_count"], row["total_matches"]) for row in direct["character_stats"]],
            [(row["id"], row["count"], row["win_count"], row["total_matches"]) for row in snapshot_cross["character_stats"]],
        )

        self.tournament.publication_status = "draft"
        self.db.commit()
        first_cached = main.get_dashboard_stats(self.tournament.id, None, self.db, self.user)
        cache_key = main._dashboard_cache_key(self.tournament.id, "stats", {"seed": None})
        self.assertIn(cache_key, main._dashboard_cache)
        self.assertIs(main.get_dashboard_stats(self.tournament.id, None, self.db, self.user), first_cached)
        main.invalidate_dashboard_cache(self.tournament.id)
        self.assertNotIn(cache_key, main._dashboard_cache)
        refreshed = main.get_dashboard_stats(self.tournament.id, None, self.db, self.user)
        self.assertEqual(refreshed, first_cached)

    def test_raw_cross_tournament_stats_succeeds_without_snapshot(self):
        """Raw cross-tournament aggregation remains available without Snapshot."""
        result = main.get_cross_tournament_stats(
            main.CrossTournamentRequest(tournament_ids=[self.tournament.id]),
            self.db,
        )
        self.assertEqual((result["total_players"], result["total_matches"]), (64, 63))
        # The legacy fixture records one RoundResult per Match.  Phase 5B must
        # count stored rows rather than assuming five rounds for full_64 data.
        self.assertEqual(result["registration_breakdown"]["total_round_results"], 63)


class FrontendFull64ContractTest(unittest.TestCase):
    """Static source-contract checks; these do not execute React components."""

    def test_static_source_contract_uses_backend_player_adoption_metrics(self):
        frontend = BACKEND_DIR.parent / "frontend" / "src" / "app"
        for relative_path in (Path("page.tsx"), Path("tournament/[id]/dashboard/page.tsx")):
            source = (frontend / relative_path).read_text(encoding="utf-8")
            self.assertNotRegex(source, r"const\s+totalPlayers\s*=\s*64\s*;")
            self.assertIn("adoptionDisplay(team, totalPlayers)", source)
            self.assertIn("adoption.playerCount", source)
            self.assertIn("adoption.adoptionRate", source)

    def test_static_source_contract_keeps_first_player_as_attacker_left_side(self):
        source = (BACKEND_DIR.parent / "frontend/src/app/tournament/[id]/page.tsx").read_text(encoding="utf-8")
        self.assertRegex(source, r"setAttackerSeed\(s1\)")
        self.assertRegex(source, r"setDefenderSeed\(s2\)")
        self.assertRegex(
            source,
            r"handlePairClick\(\s*p1\.original_seed\s*\|\|\s*p1\.seed\s*,\s*"
            r"p2\.original_seed\s*\|\|\s*p2\.seed\s*,\s*label\s*\)",
        )


if __name__ == "__main__":
    unittest.main()
