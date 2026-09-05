"""Read-only Character template audit.

Run with an explicit DATABASE_URL:
  DATABASE_URL=postgresql://... python scripts/audit_character_templates.py
The command prints counts, IDs and filenames only; it always rolls back.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import SessionLocal  # noqa: E402
import models  # noqa: E402
from services.template_management import list_template_paths, parse_template_name, template_sha256  # noqa: E402


def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")
    upload_root = Path(os.environ.get("UPLOAD_DIR", "uploads"))
    active = list_template_paths(upload_root / "templates")
    quarantine = list_template_paths(upload_root / "template_quarantine")
    db = SessionLocal()
    try:
        if db.bind.dialect.name == "postgresql":
            db.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
        pending = db.query(models.CharacterTemplateReview).filter(models.CharacterTemplateReview.status == "pending").all()
        by_character = Counter(parse_template_name(path.name).character_id for path in active)
        digest_files = defaultdict(list)
        for path in active + quarantine:
            digest_files[template_sha256(path)].append(path.name)
        referenced = {review.matched_template_filename for review in pending}
        existing = {path.name for path in active + quarantine}
        print({
            "active_count": len(active),
            "quarantine_count": len(quarantine),
            "pending_review_count": len(pending),
            "total_bytes": sum(path.stat().st_size for path in active + quarantine),
            "active_by_character": dict(sorted(by_character.items())),
            "db_references_without_file": sorted(referenced - existing),
            "duplicate_sha256": [names for names in digest_files.values() if len(names) > 1],
        })
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
