"""Phase 3A tests for champion-eight slots and player-id retrieval."""

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

if "database" in sys.modules and not hasattr(sys.modules["database"], "Base"):
    for module_name in ("main", "schemas", "models", "database"):
        sys.modules.pop(module_name, None)

from fastapi import HTTPException  # noqa: E402
from pydantic import TypeAdapter, ValidationError  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402


class ChampionSlotsApiTest(unittest.TestCase):
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
        self.owner = self._user("owner@example.invalid", "contributor")
        self.admin = self._user("admin@example.invalid", "admin")
        self.other = self._user("other@example.invalid", "contributor")
        self.champion = self._tournament("champion", "champion_8", self.owner)
        self.other_champion = self._tournament("other champion", "champion_8", self.other)
        self.full = self._tournament("full", "full_64", self.owner)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        main._dashboard_cache.clear()

    def _user(self, email, role):
        user = models.AppUser(
            email=email,
            hashed_password="unused",
            role=role,
            approval_status="approved",
        )
        self.db.add(user)
        self.db.flush()
        return user

    def _tournament(self, name, scope, owner, published=False):
        tournament = models.Tournament(
            name=name,
            date=date(2026, 1, 1),
            registration_scope=scope,
            created_by=owner.id,
            publication_status="published" if published else "draft",
        )
        self.db.add(tournament)
        self.db.flush()
        return tournament

    def _body(self, seed_number):
        return schemas.ChampionSlotUpsert(seed_number=seed_number)

    def _upsert(self, tournament, slot, seed_number, user=None):
        return main.upsert_champion_slot(
            tournament.id,
            slot,
            self._body(seed_number),
            self.db,
            user or self.owner,
        )

    def _assert_http_status(self, expected_status, function, *args):
        with self.assertRaises(HTTPException) as raised:
            function(*args)
        self.assertEqual(raised.exception.status_code, expected_status)
        return raised.exception

    def test_slot_list_always_returns_ordered_eight_slots_and_registered_players(self):
        seed_player = self._upsert(self.champion, 2, 9)
        unknown_player = self._upsert(self.champion, 8, None)

        response = schemas.ChampionSlotsResponse.model_validate(
            main.get_champion_slots(self.champion.id, self.db, self.owner)
        )
        self.assertEqual(response.tournament_id, self.champion.id)
        self.assertEqual(response.registration_scope, "champion_8")
        self.assertEqual([slot.champion_slot for slot in response.slots], list(range(1, 9)))
        self.assertIsNone(response.slots[0].player)
        self.assertEqual(response.slots[1].player.id, seed_player.id)
        self.assertEqual(response.slots[1].player.seed_number, 9)
        self.assertEqual(response.slots[1].player.name, "Player 9")
        self.assertEqual(response.slots[7].player.id, unknown_player.id)
        self.assertIsNone(response.slots[7].player.seed_number)
        self.assertEqual(response.slots[7].player.name, "champion_slot_8")

    def test_slot_list_scope_not_found_and_view_permissions(self):
        self._assert_http_status(
            409, main.get_champion_slots, self.full.id, self.db, self.owner
        )
        self._assert_http_status(
            404, main.get_champion_slots, 999999, self.db, self.owner
        )
        self._assert_http_status(
            404, main.get_champion_slots, self.champion.id, self.db, self.other
        )
        self._assert_http_status(
            404, main.get_champion_slots, self.champion.id, self.db, None
        )

        admin_response = main.get_champion_slots(self.champion.id, self.db, self.admin)
        self.assertEqual(len(admin_response["slots"]), 8)
        self.champion.publication_status = "published"
        self.db.commit()
        owner_response = main.get_champion_slots(self.champion.id, self.db, self.owner)
        self.assertEqual(len(owner_response["slots"]), 8)

    def test_create_boundary_slots_seeds_unknowns_and_cross_tournament_reuse(self):
        slot_one = self._upsert(self.champion, 1, 1)
        slot_eight = self._upsert(self.champion, 8, 64)
        unknown_one = self._upsert(self.champion, 2, None)
        unknown_two = self._upsert(self.champion, 3, None)
        same_seed_other_tournament = main.upsert_champion_slot(
            self.other_champion.id,
            1,
            self._body(1),
            self.db,
            self.other,
        )

        self.assertIsInstance(slot_one.id, int)
        self.assertEqual((slot_one.champion_slot, slot_one.seed_number, slot_one.name), (1, 1, "Player 1"))
        self.assertEqual((slot_eight.champion_slot, slot_eight.seed_number, slot_eight.name), (8, 64, "Player 64"))
        self.assertEqual((unknown_one.seed_number, unknown_one.name), (None, "champion_slot_2"))
        self.assertEqual((unknown_two.seed_number, unknown_two.name), (None, "champion_slot_3"))
        self.assertEqual(same_seed_other_tournament.seed_number, 1)

    def test_each_slot_accepts_only_its_seed_range_or_unknown(self):
        for slot in range(1, 9):
            minimum = (slot - 1) * 8 + 1
            maximum = slot * 8
            for seed in (minimum, maximum, None):
                tournament = models.Tournament(
                    name=f"slot-{slot}-{seed}", date=date(2026, 1, 1),
                    registration_scope="champion_8", created_by=self.owner.id,
                )
                self.db.add(tournament)
                self.db.commit()
                player = main.upsert_champion_slot(
                    tournament.id, slot, self._body(seed), self.db, self.owner
                )
                self.assertEqual(player.seed_number, seed)

            for seed in (minimum - 1, maximum + 1):
                if not 1 <= seed <= 64:
                    continue
                tournament = models.Tournament(
                    name=f"invalid-slot-{slot}-{seed}", date=date(2026, 1, 1),
                    registration_scope="champion_8", created_by=self.owner.id,
                )
                self.db.add(tournament)
                self.db.commit()
                self._assert_http_status(
                    422, main.upsert_champion_slot, tournament.id, slot,
                    self._body(seed), self.db, self.owner,
                )

    def test_updates_keep_player_id_generate_name_are_idempotent_and_invalidate_cache(self):
        player = self._upsert(self.champion, 1, 2)
        original_id = player.id
        cache_key = main._dashboard_cache_key(self.champion.id, "stats")
        main._dashboard_cache[cache_key] = {"value": {}, "expires_at": float("inf")}

        changed_seed = self._upsert(self.champion, 1, 3)
        self.assertEqual((changed_seed.id, changed_seed.name), (original_id, "Player 3"))
        self.assertNotIn(cache_key, main._dashboard_cache)

        changed_to_unknown = self._upsert(self.champion, 1, None)
        self.assertEqual((changed_to_unknown.id, changed_to_unknown.name), (original_id, "champion_slot_1"))

        changed_to_known = self._upsert(self.champion, 1, 4)
        self.assertEqual((changed_to_known.id, changed_to_known.name), (original_id, "Player 4"))

        with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
            repeated = self._upsert(self.champion, 1, 4)
        self.assertEqual(repeated.id, original_id)
        self.assertEqual(repeated.name, "Player 4")
        commit.assert_called_once_with()

    def test_cache_invalidation_failure_is_logged_without_failing_committed_update(self):
        with (
            patch.object(self.db, "commit", wraps=self.db.commit) as commit,
            patch.object(
                main,
                "invalidate_dashboard_cache",
                side_effect=RuntimeError("simulated cache failure"),
            ),
            patch("builtins.print") as log,
        ):
            player = self._upsert(self.champion, 5, 33)

        self.assertEqual((player.seed_number, player.name), (33, "Player 33"))
        commit.assert_called_once_with()
        stored = self.db.query(models.Player).filter_by(id=player.id).one()
        self.assertEqual((stored.seed_number, stored.name), (33, "Player 33"))
        log.assert_called_once()
        log_message = log.call_args.args[0]
        self.assertIn(f"tournament={self.champion.id}", log_message)
        self.assertIn("simulated cache failure", log_message)

    def test_validation_scope_and_permissions_reject_without_creating_players(self):
        for invalid_slot in (0, 9, -1):
            self._assert_http_status(
                422,
                main.upsert_champion_slot,
                self.champion.id,
                invalid_slot,
                self._body(1),
                self.db,
                self.owner,
            )
        for invalid_seed in (0, 65, -1):
            with self.assertRaises(ValidationError):
                self._body(invalid_seed)
            bypassed_body = schemas.ChampionSlotUpsert.model_construct(seed_number=invalid_seed)
            self._assert_http_status(
                422,
                main.upsert_champion_slot,
                self.champion.id,
                1,
                bypassed_body,
                self.db,
                self.owner,
            )
        with self.assertRaises(ValidationError):
            schemas.ChampionSlotUpsert(seed_number=1, name="User supplied name")

        self._assert_http_status(
            409,
            main.upsert_champion_slot,
            self.full.id,
            1,
            self._body(1),
            self.db,
            self.owner,
        )
        self._assert_http_status(
            403,
            main.upsert_champion_slot,
            self.champion.id,
            1,
            self._body(1),
            self.db,
            self.other,
        )
        self._assert_http_status(
            401,
            main.upsert_champion_slot,
            self.champion.id,
            1,
            self._body(1),
            self.db,
            None,
        )
        self.assertEqual(
            self.db.query(models.Player).filter_by(tournament_id=self.full.id).count(),
            0,
        )

    def test_non_integer_slot_path_is_rejected_by_pydantic_integer_validation(self):
        self.assertIs(
            main.upsert_champion_slot.__annotations__["champion_slot"],
            int,
        )
        with self.assertRaises(ValidationError):
            TypeAdapter(int).validate_python("not-a-number")

    def test_fastapi_routes_are_registered_without_seed_route_collision(self):
        expected = (
            (
                "GET",
                "/api/tournaments/{tournament_id}/champion-slots",
                main.get_champion_slots,
            ),
            (
                "PUT",
                "/api/tournaments/{tournament_id}/champion-slots/{champion_slot}",
                main.upsert_champion_slot,
            ),
            (
                "GET",
                "/api/tournaments/{tournament_id}/players/by-id/{player_id}",
                main.get_champion_player_by_id,
            ),
        )
        for method, path, endpoint in expected:
            matches = [
                route
                for route in main.app.routes
                if getattr(route, "path", None) == path
                and method in (getattr(route, "methods", None) or set())
            ]
            self.assertEqual(len(matches), 1)
            self.assertIs(matches[0].endpoint, endpoint)

        seed_details = next(
            route
            for route in main.app.routes
            if getattr(route, "path", None)
            == "/api/tournaments/{tournament_id}/players/{seed_number}/details"
        )
        player_by_id = next(
            route
            for route in main.app.routes
            if getattr(route, "path", None)
            == "/api/tournaments/{tournament_id}/players/by-id/{player_id}"
        )
        self.assertIs(seed_details.endpoint, main.get_player_details)
        self.assertIs(player_by_id.endpoint, main.get_champion_player_by_id)
        self.assertNotEqual(seed_details.path, player_by_id.path)

    def test_cross_slot_seed_is_rejected_and_integrity_conflict_rolls_back(self):
        first = self._upsert(self.champion, 1, 1)
        second = self._upsert(self.champion, 2, 9)
        self._assert_http_status(
            422,
            main.upsert_champion_slot,
            self.champion.id,
            2,
            self._body(1),
            self.db,
            self.owner,
        )
        self.db.refresh(second)
        self.assertEqual((second.seed_number, second.name), (9, "Player 9"))

        conflict = IntegrityError("UPDATE players", {}, Exception("simulated unique conflict"))
        with patch.object(self.db, "commit", side_effect=conflict):
            self._assert_http_status(
                409,
                main.upsert_champion_slot,
                self.champion.id,
                1,
                self._body(2),
                self.db,
                self.owner,
            )
        self.db.refresh(first)
        self.assertEqual((first.seed_number, first.name), (1, "Player 1"))

    def test_player_id_detail_requires_membership_and_supports_unknown_seed(self):
        unknown = self._upsert(self.champion, 4, None)
        response = schemas.ChampionPlayerResponse.model_validate(
            main.get_champion_player_by_id(
                self.champion.id, unknown.id, self.db, self.owner
            )
        )
        self.assertEqual(response.id, unknown.id)
        self.assertEqual(response.tournament_id, self.champion.id)
        self.assertEqual(response.champion_slot, 4)
        self.assertIsNone(response.seed_number)
        self.assertEqual(response.name, "champion_slot_4")

        other_player = main.upsert_champion_slot(
            self.other_champion.id,
            1,
            self._body(1),
            self.db,
            self.other,
        )
        self._assert_http_status(
            404,
            main.get_champion_player_by_id,
            self.champion.id,
            other_player.id,
            self.db,
            self.owner,
        )

    def test_existing_seed_based_player_details_remain_unchanged(self):
        self.full.publication_status = "published"
        player = models.Player(
            tournament_id=self.full.id,
            seed_number=7,
            name="Player 7",
        )
        self.db.add(player)
        self.db.commit()
        details = main.get_player_details(self.full.id, 7, self.db, self.owner)
        self.assertEqual(details["player"]["id"], player.id)
        self.assertEqual(details["player"]["seed_number"], 7)
        self.assertEqual(details["decks"], [])


if __name__ == "__main__":
    unittest.main()
