"""Phase 5B result-service and registration-scope aggregation tests."""

from collections import Counter
from datetime import date
import os
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from services.champion_snapshot import enrich_champion_snapshot_stats  # noqa: E402
from services.tournament_results import calculate_player_results  # noqa: E402
from scripts.audit_champion_registration import run as run_registration_audit  # noqa: E402
from tests.test_full64_regression import _match_pairs  # noqa: E402


class CrossScopePhase5BTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.user = models.AppUser(email="phase5b@example.invalid", hashed_password="x", role="admin", approval_status="approved")
        self.db.add(self.user)
        self.db.add_all([models.Character(id=index, name=f"C{index}") for index in range(1, 26)])
        self.db.flush()
        self.full = self._tournament("full", "full_64")
        self.champion = self._tournament("champion", "champion_8")
        self.full_players = self._players(self.full, 64, champion=False)
        self.champion_players = self._players(self.champion, 8, champion=True)
        self._full_matches(); self._champion_matches(); self.db.commit()

    def tearDown(self):
        self.db.close(); main._dashboard_cache.clear()

    def _tournament(self, name, scope):
        tournament = models.Tournament(
            name=name, date=date(2026, 1, 1), registration_scope=scope,
            publication_status="published", created_by=self.user.id,
        )
        self.db.add(tournament); self.db.flush(); return tournament

    def _players(self, tournament, count, champion):
        players = {}
        for number in range(1, count + 1):
            player = models.Player(
                tournament_id=tournament.id, seed_number=number,
                champion_slot=number if champion else None, name=f"Player {number}",
            )
            self.db.add(player); self.db.flush(); players[number] = player
            deck_set = models.DeckSet(player_id=player.id); self.db.add(deck_set); self.db.flush()
            for team_number in range(1, 6):
                first = (team_number - 1) * 5 + 1
                self.db.add(models.DeckTeam(
                    deck_set_id=deck_set.id, team_number=team_number,
                    char1_id=first, char2_id=first + 1, char3_id=first + 2,
                    char4_id=first + 3, char5_id=first + 4,
                ))
        return players

    def _full_matches(self):
        for stage, left, right in _match_pairs():
            match = models.Match(
                tournament_id=self.full.id, stage=stage,
                attacker_id=self.full_players[left].id,
                defender_id=self.full_players[right].id,
                winner_id=self.full_players[left].id,
            )
            self.db.add(match); self.db.flush()
            self.db.add(models.RoundResult(match_id=match.id, round_number=1, winner_id=match.winner_id))

    def _add_champion_match(self, stage, slot, left, right):
        match = models.Match(
            tournament_id=self.champion.id, stage=f"{stage}-{slot}",
            bracket_stage=stage, bracket_slot=slot,
            attacker_id=self.champion_players[left].id,
            defender_id=self.champion_players[right].id,
            winner_id=self.champion_players[left].id,
        )
        self.db.add(match); self.db.flush()
        for number in range(1, 6):
            self.db.add(models.RoundResult(
                match_id=match.id, round_number=number,
                winner_id=match.attacker_id if number <= 3 else match.defender_id,
            ))

    def _champion_matches(self):
        self._add_champion_match("quarterfinal", 1, 1, 2)
        self._add_champion_match("quarterfinal", 2, 3, 4)
        self._add_champion_match("quarterfinal", 3, 5, 6)
        self._add_champion_match("quarterfinal", 4, 7, 8)
        self._add_champion_match("semifinal", 1, 1, 3)
        self._add_champion_match("semifinal", 2, 5, 7)
        self._add_champion_match("final", 1, 1, 5)

    def _request(self, scope="all"):
        return main.CrossTournamentRequest(
            tournament_ids=[self.full.id, self.champion.id],
            registration_scope=scope,
        )

    def test_common_result_distributions_and_incomplete_champion_default(self):
        full = calculate_player_results(self.full, list(self.full_players.values()), list(self.full.matches))
        champion = calculate_player_results(self.champion, list(self.champion_players.values()), list(self.champion.matches))
        self.assertEqual(Counter(full.values()), {
            "best64": 32, "best32": 16, "best16": 8, "best8": 4,
            "best4": 2, "runner_up": 1, "champion": 1,
        })
        self.assertEqual(Counter(champion.values()), {"best8": 4, "best4": 2, "runner_up": 1, "champion": 1})
        self.db.query(models.Match).filter(models.Match.tournament_id == self.champion.id).delete(synchronize_session=False)
        self.db.flush()
        incomplete = calculate_player_results(self.champion, list(self.champion_players.values()), [])
        self.assertEqual(set(incomplete.values()), {"best8"})

    def test_raw_all_and_scope_filters_return_real_breakdown(self):
        mixed = main.get_cross_tournament_stats(self._request(), self.db)
        self.assertEqual((mixed["total_players"], mixed["total_matches"]), (72, 70))
        self.assertEqual(mixed["registration_breakdown"], {
            "total_tournaments": 2, "full_64_tournaments": 1, "champion_8_tournaments": 1,
            "total_registered_players": 72, "full_64_registered_players": 64,
            "champion_8_registered_players": 8, "total_teams": 360,
            "total_matches": 70, "total_round_results": 98,
        })
        full = main.get_cross_tournament_stats(self._request("full_64"), self.db)
        champion = main.get_cross_tournament_stats(self._request("champion_8"), self.db)
        self.assertEqual((full["total_players"], full["total_matches"]), (64, 63))
        self.assertEqual((champion["total_players"], champion["total_matches"]), (8, 7))
        omitted = main.CrossTournamentRequest(tournament_ids=[self.full.id, self.champion.id])
        self.assertEqual(main.get_cross_tournament_stats(omitted, self.db)["total_players"], 72)

    def test_invalid_scope_and_empty_scope_result(self):
        with self.assertRaises(ValidationError):
            main.CrossTournamentRequest(registration_scope="invalid")
        empty = main.get_cross_tournament_stats(
            main.CrossTournamentRequest(tournament_ids=[self.full.id], registration_scope="champion_8"), self.db
        )
        self.assertEqual(empty["registration_breakdown"]["total_tournaments"], 0)
        self.assertEqual(empty["character_stats"], [])

    def test_count_player_count_and_actual_player_denominator(self):
        # Duplicate one canonical team inside one player. Occurrences rise but
        # distinct adopters and adoption rate must remain bounded by 72 players.
        deck_set = self.full_players[1].deck_sets[0]
        teams = sorted(deck_set.teams, key=lambda team: team.team_number)
        for index in range(1, 6):
            setattr(teams[1], f"char{index}_id", getattr(teams[0], f"char{index}_id"))
        self.db.commit()
        result = main.get_cross_tournament_stats(self._request(), self.db)
        team = next(item for item in result["team_usage"] if item["canonical_id"] == "1,2,3,4,5")
        character = next(item for item in result["character_stats"] if item["id"] == 1)
        self.assertEqual((team["count"], team["player_count"], team["adoption_rate"]), (73, 72, 100.0))
        self.assertEqual((character["count"], character["player_count"], character["adoption_rate"]), (73, 72, 100.0))

    def test_underfilled_full64_uses_registered_players_not_fixed_64(self):
        underfilled = self._tournament("underfilled", "full_64")
        self._players(underfilled, 2, champion=False)
        self.db.commit()

        result = main.get_cross_tournament_stats(
            main.CrossTournamentRequest(
                tournament_ids=[underfilled.id], registration_scope="full_64"
            ),
            self.db,
        )

        self.assertEqual(result["total_players"], 2)
        self.assertEqual(result["registration_breakdown"]["total_registered_players"], 2)
        character = next(item for item in result["character_stats"] if item["id"] == 1)
        team = result["team_usage"][0]
        self.assertEqual(character["player_count"], 2)
        self.assertEqual(character["adoption_rate"], 100.0)
        self.assertEqual(team["player_count"], 2)
        self.assertEqual(team["adoption_rate"], 100.0)

    def test_mixed_adoption_rate_is_weighted_by_registered_players(self):
        for player in list(self.full_players.values())[:32]:
            player.deck_sets[0].teams[0].char1_id = 25
        self.db.commit()

        all_stats = main.get_cross_tournament_stats(self._request(), self.db)
        full_stats = main.get_cross_tournament_stats(self._request("full_64"), self.db)
        champion_stats = main.get_cross_tournament_stats(self._request("champion_8"), self.db)

        def rates(stats):
            character = next(row for row in stats["character_stats"] if row["id"] == 1)
            team = next(row for row in stats["team_usage"] if row["character_ids"] == [1, 2, 3, 4, 5])
            return character["player_count"], character["adoption_rate"], team["player_count"], team["adoption_rate"]

        self.assertEqual(rates(all_stats), (40, 55.6, 40, 55.6))
        self.assertEqual(rates(full_stats), (32, 50.0, 32, 50.0))
        self.assertEqual(rates(champion_stats), (8, 100.0, 8, 100.0))

    def test_new_old_and_missing_snapshots_fall_back_per_tournament_without_double_counting(self):
        third = self._tournament("third", "full_64")
        self._players(third, 2, champion=False)
        self.db.commit()
        tournament_ids = [self.full.id, self.champion.id, third.id]

        main.save_snapshot(self.full.id, main._compute_dashboard_stats(self.full.id, self.db, self.user), self.db)
        champion_stats = enrich_champion_snapshot_stats(
            main._compute_dashboard_stats(self.champion.id, self.db, self.user), self.champion.id, self.db
        )
        main.save_snapshot(self.champion.id, champion_stats, self.db)
        old = self.db.query(models.TournamentSnapshot).filter_by(tournament_id=self.champion.id).one()
        old_teams = [dict(row) for row in old.team_usage]
        old_teams[0].pop("player_count")
        old.team_usage = old_teams
        self.db.commit()

        request = main.CrossTournamentRequest(tournament_ids=tournament_ids)
        with patch.object(main, "_compute_cross_tournament_stats", wraps=main._compute_cross_tournament_stats) as compute:
            hybrid = main.get_cross_tournament_stats(request, self.db)
            compute.assert_called_once_with([self.champion.id, third.id], self.db)

        self.db.query(models.TournamentSnapshot).delete(synchronize_session=False)
        self.db.commit()
        raw = main.get_cross_tournament_stats(request, self.db)

        for key in ("total_players", "total_matches", "registration_breakdown", "character_usage_by_result"):
            self.assertEqual(hybrid[key], raw[key])
        for collection, identity in (("character_stats", "id"), ("team_usage", "canonical_id")):
            fields = (identity, "count", "player_count", "adoption_rate", "win_count", "total_matches", "best_result")
            normalize = lambda rows: sorted(tuple(row.get(field) for field in fields) for row in rows)
            self.assertEqual(normalize(hybrid[collection]), normalize(raw[collection]))

    def test_current_schema_audit_reports_counts_without_modifying_data(self):
        before = self.db.query(models.Tournament).count()
        report = run_registration_audit(self.db)
        self.assertEqual(report["tournaments_by_registration_scope"], {"full_64": 1, "champion_8": 1})
        self.assertEqual(report["published_champion_count_mismatch"]["count"], 0)
        self.assertEqual(report["legacy_snapshot_raw_fallback_tournament_ids"], [])
        self.assertEqual(self.db.query(models.Tournament).count(), before)

    def test_empty_partial_null_and_malformed_snapshots_fall_back_as_whole_tournament(self):
        expected = main._compute_cross_tournament_stats([self.full.id], self.db)
        valid = main._compute_dashboard_stats(self.full.id, self.db, self.user)
        cases = {
            "both_empty": ([], []),
            "char_empty": ([], valid["team_usage"]),
            "team_empty": (valid["character_stats"], []),
            "partial_player_count": (
                [{**row, **({} if index else {"player_count": row["player_count"]})}
                 if index == 0 else {key: value for key, value in row.items() if key != "player_count"}
                 for index, row in enumerate(valid["character_stats"])],
                valid["team_usage"],
            ),
            "null_json": (None, None),
            "dict_and_string": ({"unexpected": True}, "broken"),
        }
        for label, (char_stats, team_usage) in cases.items():
            with self.subTest(label=label):
                self.db.query(models.TournamentSnapshot).filter_by(tournament_id=self.full.id).delete()
                self.db.add(models.TournamentSnapshot(
                    tournament_id=self.full.id, total_players=64, total_matches=63,
                    char_stats=char_stats, team_usage=team_usage,
                ))
                self.db.commit()
                request = main.CrossTournamentRequest(tournament_ids=[self.full.id])
                with patch.object(main, "_compute_cross_tournament_stats", wraps=main._compute_cross_tournament_stats) as compute:
                    actual = main.get_cross_tournament_stats(request, self.db)
                    compute.assert_called_once_with([self.full.id], self.db)
                self.assertEqual(actual["total_players"], expected["total_players"])
                self.assertEqual(actual["character_stats"], expected["character_stats"])
                self.assertEqual(actual["team_usage"], expected["team_usage"][:50])

    def test_genuinely_empty_tournament_may_use_empty_snapshot(self):
        empty = self._tournament("empty", "full_64")
        self.db.flush()
        snapshot = models.TournamentSnapshot(
            tournament_id=empty.id, total_players=0, total_matches=0,
            char_stats=[], team_usage=[],
        )
        self.db.add(snapshot)
        self.db.commit()
        self.assertTrue(main.cross_snapshot_has_distinct_counts(snapshot, self.db))
        with patch.object(main, "_compute_cross_tournament_stats", wraps=main._compute_cross_tournament_stats) as compute:
            result = main.get_cross_tournament_stats(
                main.CrossTournamentRequest(tournament_ids=[empty.id]), self.db
            )
            compute.assert_not_called()
        self.assertEqual(result["total_players"], 0)
        self.assertEqual(result["character_stats"], [])

    @unittest.skipUnless(os.environ.get("AUDIT_TEST_DATABASE_URL"), "requires disposable PostgreSQL 15")
    def test_audit_cli_on_current_postgresql_schema_is_read_only(self):
        url = os.environ["AUDIT_TEST_DATABASE_URL"]
        pg_engine = create_engine(url)
        PgSession = sessionmaker(bind=pg_engine)
        Base.metadata.drop_all(pg_engine)
        Base.metadata.create_all(pg_engine)
        pg = PgSession()
        try:
            pg.add_all([models.Character(id=index, name=f"PG{index}") for index in range(1, 26)])
            full = models.Tournament(name="full draft", date=date(2026, 1, 1), registration_scope="full_64", publication_status="draft")
            good = models.Tournament(name="champion published", date=date(2026, 1, 1), registration_scope="champion_8", publication_status="published")
            missing = models.Tournament(name="champion missing", date=date(2026, 1, 1), registration_scope="champion_8", publication_status="draft")
            pg.add_all([full, good, missing]); pg.flush()
            full_player = models.Player(tournament_id=full.id, seed_number=1, name="Player 1")
            pg.add(full_player); pg.flush()
            full_deck_set = models.DeckSet(player_id=full_player.id)
            pg.add(full_deck_set); pg.flush()
            pg.add(models.DeckTeam(
                deck_set_id=full_deck_set.id, team_number=1,
                char1_id=1, char2_id=2, char3_id=3, char4_id=4, char5_id=5,
            ))
            good_players = []
            for slot in range(1, 9):
                player = models.Player(tournament_id=good.id, champion_slot=slot, seed_number=slot, name=f"Player {slot}")
                pg.add(player); pg.flush(); good_players.append(player)
                deck_set = models.DeckSet(player_id=player.id); pg.add(deck_set); pg.flush()
                for team_number in range(1, 6):
                    start = (team_number - 1) * 5 + 1
                    pg.add(models.DeckTeam(
                        deck_set_id=deck_set.id, team_number=team_number,
                        **{f"char{position}_id": start + position - 1 for position in range(1, 6)},
                    ))
            for slot in range(1, 8):
                pg.add(models.Player(tournament_id=missing.id, champion_slot=slot, seed_number=slot, name=f"Player {slot}"))
            match_pairs = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (4, 6), (0, 4)]
            match_keys = [("quarterfinal", i) for i in range(1, 5)] + [("semifinal", i) for i in range(1, 3)] + [("final", 1)]
            for (left, right), (stage, slot) in zip(match_pairs, match_keys):
                match = models.Match(
                    tournament_id=good.id, stage="champion", bracket_stage=stage, bracket_slot=slot,
                    attacker_id=good_players[left].id, defender_id=good_players[right].id,
                    winner_id=good_players[left].id,
                )
                pg.add(match); pg.flush()
                for round_number in range(1, 6):
                    pg.add(models.RoundResult(match_id=match.id, round_number=round_number, winner_id=good_players[left].id))
            pg.add(models.TournamentSnapshot(
                tournament_id=full.id, total_players=1, total_matches=0,
                char_stats=[{"id": 1, "count": 1, "player_count": 1}],
                team_usage=[{"canonical_id": "1,2,3,4,5", "count": 1, "player_count": 1}], matchups=[],
            ))
            pg.add(models.TournamentSnapshot(
                tournament_id=good.id, total_players=8, total_matches=7,
                char_stats=[{"id": 1, "count": 8}],
                team_usage=[{"canonical_id": "1,2,3,4,5", "count": 8}], matchups=[],
            ))
            pg.commit()

            duplicate_rejected = False
            try:
                with pg.begin_nested():
                    pg.add(models.Player(tournament_id=missing.id, champion_slot=8, seed_number=1, name="duplicate"))
                    pg.flush()
            except IntegrityError:
                duplicate_rejected = True
            self.assertTrue(duplicate_rejected)
            pg.rollback()

            tables = (models.Tournament, models.Player, models.DeckSet, models.DeckTeam, models.Match, models.RoundResult, models.TournamentSnapshot)
            before = [pg.query(table).count() for table in tables]
            completed = subprocess.run(
                [sys.executable, "scripts/audit_champion_registration.py"],
                cwd=BACKEND_DIR, env={**os.environ, "DATABASE_URL": url},
                text=True, capture_output=True, check=True,
            )
            report = __import__("json").loads(completed.stdout)
            after = [pg.query(table).count() for table in tables]
            self.assertEqual(after, before)
            self.assertEqual(report["legacy_snapshot_raw_fallback_tournament_ids"], [good.id])
            self.assertIn(str(good.id), report["snapshot_comparison"])
            self.assertNotIn(url, completed.stdout)
            self.assertNotIn(url, completed.stderr)

            old_snapshot = pg.query(models.TournamentSnapshot).filter_by(tournament_id=good.id).one()
            old_snapshot.team_usage = "intentionally malformed"
            pg.commit()
            exception_before = [pg.query(table).count() for table in tables]
            failed = subprocess.run(
                [sys.executable, "scripts/audit_champion_registration.py"],
                cwd=BACKEND_DIR, env={**os.environ, "DATABASE_URL": url},
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual([pg.query(table).count() for table in tables], exception_before)
            self.assertNotIn(url, failed.stdout + failed.stderr)
            self.assertNotIn("audit-test-only", failed.stdout + failed.stderr)

            pg.add(models.Tournament(name="rollback probe", date=date(2026, 1, 1)))
            pg.flush(); pg.rollback()
            self.assertEqual([pg.query(table).count() for table in tables], exception_before)
        finally:
            pg.close()
            Base.metadata.drop_all(pg_engine)
            pg_engine.dispose()

    def test_snapshot_and_raw_paths_match_and_old_snapshot_falls_back(self):
        raw = main.get_cross_tournament_stats(self._request(), self.db)
        full_stats = main._compute_dashboard_stats(self.full.id, self.db, self.user)
        main.save_snapshot(self.full.id, full_stats, self.db)
        champion_stats = enrich_champion_snapshot_stats(
            main._compute_dashboard_stats(self.champion.id, self.db, self.user), self.champion.id, self.db
        )
        main.save_snapshot(self.champion.id, champion_stats, self.db)
        snapshot = main.get_cross_tournament_stats(self._request(), self.db)
        for key in ("total_players", "total_matches", "registration_breakdown"):
            self.assertEqual(snapshot[key], raw[key])
        self.assertEqual(
            [(row["id"], row["count"], row["player_count"], row["win_count"], row["total_matches"], row["best_result"]) for row in snapshot["character_stats"]],
            [(row["id"], row["count"], row["player_count"], row["win_count"], row["total_matches"], row["best_result"]) for row in raw["character_stats"]],
        )
        self.assertEqual(
            [(row["character_ids"], row["count"], row["player_count"], row["win_count"], row["total_matches"], row["best_result"]) for row in snapshot["team_usage"]],
            [(row["character_ids"], row["count"], row["player_count"], row["win_count"], row["total_matches"], row["best_result"]) for row in raw["team_usage"]],
        )
        self.assertEqual(snapshot["character_usage_by_result"], raw["character_usage_by_result"])
        old = self.db.query(models.TournamentSnapshot).filter_by(tournament_id=self.full.id).one()
        old.char_stats = [{key: value for key, value in row.items() if key != "player_count"} for row in old.char_stats]
        self.db.commit()
        with patch.object(main, "_compute_cross_tournament_stats", wraps=main._compute_cross_tournament_stats) as compute:
            legacy = main.get_cross_tournament_stats(self._request(), self.db)
            compute.assert_called_once()
        self.assertEqual(legacy["total_players"], 72)


if __name__ == "__main__":
    unittest.main()
