"""Phase 2B tests for Tournament create, update, and retrieval APIs."""

from datetime import date
import os
from pathlib import Path
import sys
import unittest


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DASHBOARD_CACHE_TTL_SECONDS", "60")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if "database" in sys.modules and not hasattr(sys.modules["database"], "Base"):
    for module_name in ("main", "schemas", "models", "database"):
        sys.modules.pop(module_name, None)

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402


class TournamentApiPhase2BTest(unittest.TestCase):
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
        self.owner = self._user(
            "owner@example.invalid",
            role="contributor",
            game_start_date=date(2024, 1, 2),
            provider_name="Owner",
        )
        self.admin = self._user(
            "admin@example.invalid",
            role="admin",
            game_start_date=date(2023, 3, 4),
            provider_name="Admin",
        )
        self.other = self._user(
            "other@example.invalid",
            role="contributor",
            game_start_date=date(2025, 5, 6),
            provider_name="Other",
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        main._dashboard_cache.clear()

    def _user(self, email, role, game_start_date, provider_name):
        user = models.AppUser(
            email=email,
            hashed_password="unused",
            role=role,
            game_start_date=game_start_date,
            provider_name=provider_name,
            approval_status="approved",
        )
        self.db.add(user)
        self.db.flush()
        return user

    def _payload(self, name="Tournament", **values):
        return schemas.TournamentBase(
            name=name,
            date=values.pop("date", date(2026, 1, 1)),
            **values,
        )

    def _create(self, user=None, **values):
        return main.create_tournament(
            self._payload(**values),
            self.db,
            user or self.owner,
        )

    def _assert_http_status(self, expected_status, function, *args):
        with self.assertRaises(HTTPException) as raised:
            function(*args)
        self.assertEqual(raised.exception.status_code, expected_status)
        return raised.exception

    def test_create_scope_defaults_explicit_values_validation_and_response(self):
        default_scope = self._create(name="default")
        explicit_full = self._create(name="full", registration_scope="full_64")
        champion = self._create(name="champion", registration_scope="champion_8")

        self.assertEqual(default_scope.registration_scope, "full_64")
        self.assertEqual(explicit_full.registration_scope, "full_64")
        self.assertEqual(champion.registration_scope, "champion_8")
        response = schemas.Tournament.model_validate(champion)
        self.assertEqual(response.registration_scope, "champion_8")
        self.assertEqual(response.provider_game_start_date, self.owner.game_start_date)

        with self.assertRaises(ValidationError):
            self._payload(registration_scope="invalid")

    def test_create_provider_date_omitted_explicit_proxy_and_null(self):
        inherited = self._create(name="inherited")
        explicit_date = self._create(
            name="proxy registration",
            provider_game_start_date=date(2022, 7, 8),
        )
        explicit_null = self._create(
            name="explicit null",
            provider_game_start_date=None,
        )
        no_profile_user = self._user(
            "no-profile-date@example.invalid",
            role="contributor",
            game_start_date=None,
            provider_name="No Date",
        )
        self.db.commit()
        no_profile = self._create(user=no_profile_user, name="no profile")

        self.assertEqual(inherited.provider_game_start_date, date(2024, 1, 2))
        self.assertEqual(explicit_date.provider_game_start_date, date(2022, 7, 8))
        self.assertIsNone(explicit_null.provider_game_start_date)
        self.assertIsNone(no_profile.provider_game_start_date)

    def test_update_scope_omission_same_value_and_conflicts_are_atomic(self):
        champion = self._create(
            name="original",
            registration_scope="champion_8",
            provider_game_start_date=date(2022, 1, 1),
        )

        omitted = main.update_tournament(
            champion.id,
            self._payload(name="owner updated", date=date(2026, 2, 2)),
            self.db,
            self.owner,
        )
        self.assertEqual(omitted.registration_scope, "champion_8")
        self.assertEqual(omitted.name, "owner updated")

        same_scope = main.update_tournament(
            champion.id,
            self._payload(name="same accepted", registration_scope="champion_8"),
            self.db,
            self.owner,
        )
        self.assertEqual(same_scope.registration_scope, "champion_8")
        self.assertEqual(same_scope.name, "same accepted")

        self._assert_http_status(
            409,
            main.update_tournament,
            champion.id,
            self._payload(
                name="must not persist",
                date=date(2030, 1, 1),
                registration_scope="full_64",
                provider_game_start_date=date(2030, 1, 2),
            ),
            self.db,
            self.owner,
        )
        self.db.refresh(champion)
        self.assertEqual(champion.name, "same accepted")
        self.assertNotEqual(champion.date, date(2030, 1, 1))
        self.assertEqual(champion.provider_game_start_date, date(2022, 1, 1))

        champion.publication_status = "published"
        self.db.add(models.Player(
            tournament_id=champion.id,
            name="existing child",
            champion_slot=1,
        ))
        self.db.commit()
        self._assert_http_status(
            409,
            main.update_tournament,
            champion.id,
            self._payload(name="admin cannot change", registration_scope="full_64"),
            self.db,
            self.admin,
        )

    def test_update_provider_date_omission_explicit_null_and_profile_isolation(self):
        tournament = self._create(
            name="dates",
            provider_game_start_date=date(2021, 1, 1),
        )
        self.owner.game_start_date = date(2035, 1, 1)
        self.db.commit()

        omitted = main.update_tournament(
            tournament.id,
            self._payload(name="date omitted"),
            self.db,
            self.owner,
        )
        self.assertEqual(omitted.provider_game_start_date, date(2021, 1, 1))

        explicit = main.update_tournament(
            tournament.id,
            self._payload(name="date explicit", provider_game_start_date=date(2020, 2, 3)),
            self.db,
            self.owner,
        )
        self.assertEqual(explicit.provider_game_start_date, date(2020, 2, 3))

        cleared = main.update_tournament(
            tournament.id,
            self._payload(name="date cleared", provider_game_start_date=None),
            self.db,
            self.owner,
        )
        self.assertIsNone(cleared.provider_game_start_date)

        self.owner.game_start_date = date(2040, 4, 4)
        self.db.commit()
        self.db.refresh(tournament)
        self.assertIsNone(tournament.provider_game_start_date)

    def test_update_permissions_not_found_and_cache_invalidation(self):
        tournament = self._create(name="permissions")

        self._assert_http_status(
            403,
            main.update_tournament,
            tournament.id,
            self._payload(name="other denied"),
            self.db,
            self.other,
        )
        self._assert_http_status(
            401,
            main.update_tournament,
            tournament.id,
            self._payload(name="anonymous denied"),
            self.db,
            None,
        )
        self._assert_http_status(
            404,
            main.update_tournament,
            999999,
            self._payload(name="missing"),
            self.db,
            self.admin,
        )

        admin_updated = main.update_tournament(
            tournament.id,
            self._payload(name="admin updated", provider_game_start_date=date(2019, 9, 9)),
            self.db,
            self.admin,
        )
        self.assertEqual(admin_updated.name, "admin updated")
        self.assertEqual(admin_updated.provider_game_start_date, date(2019, 9, 9))

        cache_key = main._dashboard_cache_key(tournament.id, "stats")
        main._dashboard_cache[cache_key] = {"value": {"stale": True}, "expires_at": float("inf")}
        owner_updated = main.update_tournament(
            tournament.id,
            self._payload(name="owner updated again"),
            self.db,
            self.owner,
        )
        self.assertEqual(owner_updated.name, "owner updated again")
        self.assertNotIn(cache_key, main._dashboard_cache)

    def test_create_get_list_and_update_responses_include_stored_values(self):
        old_full = self._create(
            name="old full",
            registration_scope="full_64",
            provider_game_start_date=None,
        )
        champion = self._create(
            name="champion",
            registration_scope="champion_8",
            provider_game_start_date=date(2020, 6, 7),
        )
        old_full.publication_status = "published"
        champion.publication_status = "published"
        self.db.commit()

        created_response = schemas.Tournament.model_validate(champion)
        single_response = schemas.Tournament.model_validate(
            main.get_tournament(champion.id, self.db, None)
        )
        list_response = main.get_tournaments(False, self.db, None)
        updated_response = schemas.Tournament.model_validate(main.update_tournament(
            champion.id,
            self._payload(
                name="champion updated",
                registration_scope="champion_8",
                provider_game_start_date=date(2021, 8, 9),
            ),
            self.db,
            self.owner,
        ))

        self.assertEqual(created_response.registration_scope, "champion_8")
        self.assertEqual(single_response.registration_scope, "champion_8")
        self.assertEqual(single_response.provider_game_start_date, date(2020, 6, 7))
        listed = {item.id: item for item in list_response}
        self.assertEqual(listed[champion.id].registration_scope, "champion_8")
        self.assertEqual(listed[champion.id].provider_game_start_date, date(2020, 6, 7))
        self.assertEqual(listed[old_full.id].registration_scope, "full_64")
        self.assertIsNone(listed[old_full.id].provider_game_start_date)
        self.assertEqual(updated_response.registration_scope, "champion_8")
        self.assertEqual(updated_response.provider_game_start_date, date(2021, 8, 9))


if __name__ == "__main__":
    unittest.main()
