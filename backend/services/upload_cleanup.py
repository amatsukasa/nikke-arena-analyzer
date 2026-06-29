import os
import shutil
import time
from pathlib import Path
from typing import Iterable


UPLOAD_ROOT = Path("uploads").resolve()
CROPPED_DIR = (UPLOAD_ROOT / "cropped").resolve()
# 永続プレイヤーアイコン保存ディレクトリ（cleanup 対象外）
PLAYER_ICONS_DIR = (UPLOAD_ROOT / "player_icons").resolve()

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
    """
    一時アップロードファイルを削除する。

    対象:
    - uploads/ 直下の tour_* / match_* 一時ファイル（stale）
    - uploads/cropped/ 内の crop_*.png（一時解析画像）
    - uploads/cropped/ 内の player_icon_*.png（未参照かつ stale）

    除外（削除しない）:
    - uploads/player_icons/ 以下は一切削除しない（永続保存領域）
    - uploads/templates/ 以下は一切削除しない（AI学習テンプレート）
    """
    cutoff = time.time() - max_age_hours * 60 * 60
    deleted = 0

    # uploads/ 直下の一時ファイルを削除
    if UPLOAD_ROOT.is_dir():
        for path in UPLOAD_ROOT.iterdir():
            if (
                path.is_file()
                and path.name.startswith(TEMP_ROOT_PREFIXES)
                and path.stat().st_mtime < cutoff
            ):
                deleted += int(delete_upload_file(path))

    # uploads/cropped/ 内の一時ファイルを削除
    # ※ uploads/player_icons/ は永続保存領域のため絶対に触らない
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


def delete_tournament_player_icons(tournament_id: int) -> int:
    """
    大会削除時に uploads/player_icons/tournament_{id}/ を丸ごと削除する。

    安全性チェック: PLAYER_ICONS_DIR 配下であることを確認してから削除する。
    """
    target_dir = (PLAYER_ICONS_DIR / f"tournament_{tournament_id}").resolve()
    if not _is_within(target_dir, PLAYER_ICONS_DIR):
        print(f"[Cleanup] Unsafe path detected, skipping: {target_dir}")
        return 0
    if not target_dir.is_dir():
        return 0
    try:
        deleted_count = sum(1 for f in target_dir.rglob("*") if f.is_file())
        shutil.rmtree(target_dir)
        print(f"[Cleanup] Deleted tournament {tournament_id} player icons: {deleted_count} files")
        return deleted_count
    except OSError as error:
        print(f"[Cleanup] Failed to delete {target_dir}: {error}")
        return 0


def cleanup_orphan_player_icons(referenced_icon_urls: set[str]) -> int:
    """
    uploads/player_icons/ 配下にあるファイルのうち、
    DB上の players.icon_url に参照が存在しないファイルのみを削除する補助関数。

    ※ 通常の stale cleanup とは独立した補助関数。必要時に手動呼び出しする。
    """
    if not PLAYER_ICONS_DIR.is_dir():
        return 0

    referenced_paths = {
        path.resolve()
        for url in referenced_icon_urls
        if (path := path_from_upload_url(url)) is not None
    }

    deleted = 0
    for path in PLAYER_ICONS_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() not in referenced_paths:
            deleted += int(delete_upload_file(path))

    if deleted:
        print(f"[Cleanup] Removed {deleted} orphan player icon files")
    return deleted


def stale_age_hours_from_env() -> int:
    raw_value = os.environ.get("UPLOAD_TEMP_MAX_AGE_HOURS", "24")
    try:
        return max(1, int(raw_value))
    except ValueError:
        return 24
