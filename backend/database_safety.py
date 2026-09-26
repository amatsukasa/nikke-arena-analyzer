"""Fail-closed database selection for automated tests."""
from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
TEST_DATABASE_HOSTS = {"db_test", *LOCAL_HOSTS}
ACCEPTANCE_DATABASE_HOSTS = {"db_acceptance", *LOCAL_HOSTS}
TEST_DATABASE_NAME = "nikke_arena_test"
ACCEPTANCE_DATABASE_NAME = "nikke_arena_acceptance"


def normalize_postgresql_driver_url(raw: str) -> str:
    """Select the installed psycopg2 driver without changing connection details."""
    scheme, separator, remainder = raw.partition("://")
    if not separator or scheme not in {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }:
        return raw
    return f"postgresql+psycopg2://{remainder}"


def is_automated_test_process(argv: list[str] | None = None) -> bool:
    arguments = argv if argv is not None else sys.argv
    if os.environ.get("NIKKE_AUTOMATED_TEST") == "1":
        return True
    return any(
        "unittest" in argument.lower()
        or "pytest" in argument.lower()
        or os.path.basename(argument).lower().startswith("test_")
        for argument in arguments
    )


def _connection_target(raw: str, label: str) -> tuple[str, str]:
    parsed = urlsplit(raw)
    if parsed.scheme not in {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }:
        raise RuntimeError(f"Refusing {label}: only PostgreSQL URLs are allowed")
    return (parsed.hostname or "").lower(), parsed.path.rsplit("/", 1)[-1].lower()


def validate_test_database_url(
    test_url: str | None,
    application_url: str | None = None,
    acceptance_url: str | None = None,
) -> str:
    if not test_url:
        raise RuntimeError("Refusing automated tests: TEST_DATABASE_URL is required")

    host, database_name = _connection_target(test_url, "automated tests")
    if host not in TEST_DATABASE_HOSTS:
        raise RuntimeError("Refusing automated tests: host is not in the local TEST DB allowlist")
    if database_name != TEST_DATABASE_NAME:
        raise RuntimeError(f"Refusing automated tests: database must be exactly '{TEST_DATABASE_NAME}'")
    if application_url and test_url == application_url:
        raise RuntimeError("Refusing automated tests: TEST_DATABASE_URL equals DATABASE_URL")
    if acceptance_url and test_url == acceptance_url:
        raise RuntimeError("Refusing automated tests: TEST_DATABASE_URL equals ACCEPTANCE_DATABASE_URL")
    return test_url


def validate_acceptance_database_url(
    acceptance_url: str | None,
    test_url: str | None = None,
) -> str:
    if not acceptance_url:
        raise RuntimeError("Refusing acceptance seed: ACCEPTANCE_DATABASE_URL is required")
    host, database_name = _connection_target(acceptance_url, "acceptance seed")
    if host not in ACCEPTANCE_DATABASE_HOSTS:
        raise RuntimeError("Refusing acceptance seed: host is not in the local acceptance DB allowlist")
    if database_name != ACCEPTANCE_DATABASE_NAME:
        raise RuntimeError(
            f"Refusing acceptance seed: database must be exactly '{ACCEPTANCE_DATABASE_NAME}'"
        )
    if test_url and acceptance_url == test_url:
        raise RuntimeError("Refusing acceptance seed: ACCEPTANCE_DATABASE_URL equals TEST_DATABASE_URL")
    return acceptance_url


def database_url_for_process() -> str:
    application_url = os.environ.get("DATABASE_URL")
    if is_automated_test_process():
        test_url = validate_test_database_url(
            os.environ.get("TEST_DATABASE_URL"),
            application_url,
            os.environ.get("ACCEPTANCE_DATABASE_URL"),
        )
        normalized_url = normalize_postgresql_driver_url(test_url)
        os.environ["DATABASE_URL"] = normalized_url
        return normalized_url
    selected_url = application_url or "postgresql://postgres:password@db:5432/nikke_arena"
    return normalize_postgresql_driver_url(selected_url)
