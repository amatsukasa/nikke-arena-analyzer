"""Fail-closed unittest runner.

Usage: DATABASE_URL=sqlite:////tmp/template_disposable_test.db \
       python scripts/run_safe_tests.py tests.test_template_management
"""
from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import urlsplit


def validated_target() -> tuple[str, str, str]:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        raise SystemExit("Refusing tests: DATABASE_URL is required")
    parsed = urlsplit(raw)
    database = parsed.path.rsplit("/", 1)[-1]
    host = parsed.hostname or "local-file"
    port = str(parsed.port or (5432 if parsed.scheme.startswith("postgres") else "n/a"))
    lowered = f"{host}/{database}".lower()
    if not any(marker in database.lower() for marker in ("test", "disposable")):
        raise SystemExit("Refusing tests: database name must contain test or disposable")
    if database.lower() == "nikke_arena" or "railway" in lowered:
        raise SystemExit("Refusing tests: target resembles an application or Railway database")
    print(f"[safe-test] target host={host} port={port} database={database}")
    return host, port, database


if __name__ == "__main__":
    validated_target()
    if len(sys.argv) < 2:
        raise SystemExit("Specify one or more unittest modules")
    raise SystemExit(subprocess.call([sys.executable, "-m", "unittest", *sys.argv[1:]]))
