import os
import time
from pathlib import Path
from typing import Iterable


UPLOAD_ROOT = Path("uploads").resolve()
CROPPED_DIR = (UPLOAD_ROOT / "cropped").resolve()
TEMP_ROOT_PREFIXES = ("tour_", "match_")
TEMP_CROP_PREFIX = "crop_"
PLAYER_ICON_PREFIX = "player_icon_"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def path_from_upload_url(url: str | None) -> Path | None:
    prefix = "/api/uploads/"
    if not url or not url.startswith(prefix):
        return None
    candidate = (UPLOAD_ROOT / url[len(prefix):]).resolve()
    if not _is_within(candidate, UPLOAD_ROOT):
        return None
    return candidate


def delete_upload_file(path: str | Path | None) -> bool:
    if not path:
        return False
    candidate = Path(path).resolve()
    if not _is_within(candidate, UPLOAD_ROOT) or not candidate.is_file():
        return False
    try:
        candidate.unlink()
        return True
    except OSError as error:
        print(f"[Cleanup] Failed to delete {candidate}: {error}")
        return False


def delete_temporary_crop_urls(urls: Iterable[str | None]) -> int:
    deleted = 0
    for url in set(urls):
        path = path_from_upload_url(url)
        if (
            path
            and _is_within(path, CROPPED_DIR)
            and path.name.startswith(TEMP_CROP_PREFIX)
        ):
            deleted += int(delete_upload_file(path))
    return deleted


def cleanup_stale_uploads(
    referenced_player_icons: set[str],
    max_age_hours: int = 24,
) -> int:
    cutoff = time.time() - max_age_hours * 60 * 60
    deleted = 0

    if UPLOAD_ROOT.is_dir():
        for path in UPLOAD_ROOT.iterdir():
            if (
                path.is_file()
                and path.name.startswith(TEMP_ROOT_PREFIXES)
                and path.stat().st_mtime < cutoff
            ):
                deleted += int(delete_upload_file(path))

    if CROPPED_DIR.is_dir():
        referenced_paths = {
            path
            for url in referenced_player_icons
            if (path := path_from_upload_url(url)) is not None
        }
        for path in CROPPED_DIR.iterdir():
            if not path.is_file() or path.stat().st_mtime >= cutoff:
                continue
            is_stale_crop = path.name.startswith(TEMP_CROP_PREFIX)
            is_unused_icon = (
                path.name.startswith(PLAYER_ICON_PREFIX)
                and path.resolve() not in referenced_paths
            )
            if is_stale_crop or is_unused_icon:
                deleted += int(delete_upload_file(path))

    if deleted:
        print(f"[Cleanup] Removed {deleted} stale upload files")
    return deleted


def stale_age_hours_from_env() -> int:
    raw_value = os.environ.get("UPLOAD_TEMP_MAX_AGE_HOURS", "24")
    try:
        return max(1, int(raw_value))
    except ValueError:
        return 24
