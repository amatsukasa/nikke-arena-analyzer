"""Dry-run or apply initial representative Character images."""
import argparse
import json
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import SessionLocal  # noqa: E402
from services.representative_images import initialize_representative_templates  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="persist selected representatives")
    parser.add_argument("--upload-dir", default="uploads")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        report = initialize_representative_templates(
            db, args.upload_dir, apply=args.apply
        )
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
