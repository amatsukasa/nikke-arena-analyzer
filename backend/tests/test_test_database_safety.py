import os
import unittest
from unittest.mock import patch

from database_safety import (
    database_url_for_process,
    is_automated_test_process,
    normalize_postgresql_driver_url,
    validate_acceptance_database_url,
    validate_test_database_url,
)


class TestDatabaseSafetyTest(unittest.TestCase):
    def test_test_process_stores_and_returns_normalized_psycopg2_url(self):
        source = "postgresql+psycopg://postgres:password@db_test:5432/nikke_arena_test"
        expected = "postgresql+psycopg2://postgres:password@db_test:5432/nikke_arena_test"
        with patch.dict(
            os.environ,
            {"NIKKE_AUTOMATED_TEST": "1", "TEST_DATABASE_URL": source},
            clear=True,
        ):
            self.assertEqual(database_url_for_process(), expected)
            self.assertEqual(os.environ["DATABASE_URL"], expected)

    def test_normalizes_postgresql_scheme_to_installed_psycopg2_driver(self):
        suffix = "user:p%40ss@db.example:5432/app?sslmode=require&x=1"
        for scheme in ("postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"):
            with self.subTest(scheme=scheme):
                self.assertEqual(
                    normalize_postgresql_driver_url(f"{scheme}://{suffix}"),
                    f"postgresql+psycopg2://{suffix}",
                )

    def test_detects_direct_test_files(self):
        self.assertTrue(is_automated_test_process(["tests/test_example.py"]))

    def test_requires_explicit_test_database_url(self):
        with self.assertRaisesRegex(RuntimeError, "TEST_DATABASE_URL is required"):
            validate_test_database_url(None, "postgresql://host/nikke_arena")

    def test_rejects_wrong_test_database_and_equal_database_urls(self):
        with self.assertRaisesRegex(RuntimeError, "must be exactly"):
            validate_test_database_url("postgresql://db_test/nikke_arena")
        target = "postgresql://db_test/nikke_arena_test"
        with self.assertRaisesRegex(RuntimeError, "equals DATABASE_URL"):
            validate_test_database_url(target, target)
        with self.assertRaisesRegex(RuntimeError, "equals ACCEPTANCE_DATABASE_URL"):
            validate_test_database_url(target, None, target)

    def test_test_database_allowlist_rejects_external_and_wrong_local_targets(self):
        rejected = (
            "postgresql://user:pass@dangerous.example.com/nikke_arena_test",
            "postgresql://user:pass@db_test/nikke_arena_test_copy",
            "postgresql://user:pass@db/nikke_arena_test",
            "postgresql://user:pass@railway.internal/nikke_arena_test",
        )
        for target in rejected:
            with self.subTest(target=target), self.assertRaises(RuntimeError):
                validate_test_database_url(target)

    def test_accepts_only_dedicated_or_loopback_test_database(self):
        for target in (
            "postgresql://postgres:password@db_test:5432/nikke_arena_test",
            "postgresql+psycopg://postgres:password@db_test:5432/nikke_arena_test",
            "postgresql://postgres:password@localhost:5433/nikke_arena_test",
            "postgresql://postgres:password@127.0.0.1:5433/nikke_arena_test",
            "postgresql://postgres:password@[::1]:5433/nikke_arena_test",
        ):
            with self.subTest(target=target):
                self.assertEqual(validate_test_database_url(target), target)

    def test_acceptance_database_allowlist(self):
        accepted = (
            "postgresql://postgres:password@db_acceptance:5432/nikke_arena_acceptance",
            "postgresql://postgres:password@localhost:5434/nikke_arena_acceptance",
            "postgresql://postgres:password@127.0.0.1:5434/nikke_arena_acceptance",
            "postgresql://postgres:password@[::1]:5434/nikke_arena_acceptance",
        )
        for target in accepted:
            with self.subTest(target=target):
                self.assertEqual(validate_acceptance_database_url(target), target)

        rejected = (
            "postgresql://user:pass@dangerous.example.com/nikke_arena_acceptance",
            "postgresql://user:pass@db_acceptance/nikke_arena_acceptance_copy",
            "postgresql://user:pass@db/nikke_arena_acceptance",
            "postgresql://user:pass@railway.internal/nikke_arena_acceptance",
        )
        for target in rejected:
            with self.subTest(target=target), self.assertRaises(RuntimeError):
                validate_acceptance_database_url(target)

    def test_acceptance_and_test_databases_must_differ(self):
        target = "postgresql://postgres:password@db_acceptance:5432/nikke_arena_acceptance"
        with self.assertRaisesRegex(RuntimeError, "equals TEST_DATABASE_URL"):
            validate_acceptance_database_url(target, target)


if __name__ == "__main__":
    unittest.main()
