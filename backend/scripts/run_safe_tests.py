"""Fail-closed unittest runner.

Usage: TEST_DATABASE_URL=postgresql://postgres:password@db_test:5432/nikke_arena_test \
       python scripts/run_safe_tests.py discover -s tests -v
"""
from __future__ import annotations

import os
import subprocess
import sys

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database_safety import validate_test_database_url  # noqa: E402


def validated_target() -> str:
    try:
        target = validate_test_database_url(
            os.environ.get("TEST_DATABASE_URL"),
            os.environ.get("DATABASE_URL"),
            os.environ.get("ACCEPTANCE_DATABASE_URL"),
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print("[safe-test] validated TEST_DATABASE_URL")
    return target


if __name__ == "__main__":
    validated_target()
    if len(sys.argv) < 2:
        raise SystemExit("Specify one or more unittest modules")
    child_environment = os.environ.copy()
    child_environment["NIKKE_AUTOMATED_TEST"] = "1"
    raise SystemExit(subprocess.call(
        [sys.executable, "-m", "unittest", *sys.argv[1:]],
        env=child_environment,
    ))
