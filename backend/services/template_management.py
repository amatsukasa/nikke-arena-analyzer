from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import os
import re
import threading
from typing import Iterator


TEMPLATE_NAME = re.compile(r"^char_(?P<char_id>\d+)(?:_(?P<generation>\d{3}))?\.png$")
_PROCESS_LOCK = threading.RLock()


@dataclass(frozen=True)
class TemplateName:
    character_id: int
    generation: int
    filename: str


def parse_template_name(filename: str) -> TemplateName:
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValueError("Invalid template filename")
    match = TEMPLATE_NAME.fullmatch(filename)
    if not match:
        raise ValueError("Invalid template filename")
    return TemplateName(
        character_id=int(match.group("char_id")),
        generation=int(match.group("generation") or 0),
        filename=filename,
    )


def safe_template_path(root: Path, filename: str, expected_character_id: int | None = None) -> Path:
    parsed = parse_template_name(filename)
    if expected_character_id is not None and parsed.character_id != expected_character_id:
        raise ValueError("Template Character does not match filename")
    root = root.resolve()
    candidate = (root / filename).resolve()
    if candidate.parent != root or candidate.is_symlink():
        raise ValueError("Unsafe template path")
    return candidate


def template_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_template_paths(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    result = []
    for path in root.iterdir():
        try:
            parse_template_name(path.name)
        except ValueError:
            continue
        if path.is_file() and not path.is_symlink():
            result.append(path)
    return sorted(result, key=lambda item: (parse_template_name(item.name).character_id, parse_template_name(item.name).generation))


def representative_template(root: Path, character_id: int) -> Path | None:
    candidates = [
        path for path in list_template_paths(root)
        if parse_template_name(path.name).character_id == character_id
    ]
    return max(candidates, key=lambda item: parse_template_name(item.name).generation, default=None)


def next_template_name(root: Path, character_id: int) -> str:
    generations = [
        parse_template_name(path.name).generation
        for path in list_template_paths(root)
        if parse_template_name(path.name).character_id == character_id
    ]
    return f"char_{character_id}_{max(generations, default=0) + 1:03d}.png"


def find_duplicate(root: Path, digest: str) -> Path | None:
    return next((path for path in list_template_paths(root) if template_sha256(path) == digest), None)


@contextmanager
def template_operation_lock(upload_root: Path) -> Iterator[None]:
    """Serialize file operations in-process and across local worker processes."""
    lock_path = upload_root.resolve() / ".template-management.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _PROCESS_LOCK, lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            import msvcrt
            lock_file.seek(0)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def describe_template(path: Path, *, active: bool, representative: bool) -> dict:
    parsed = parse_template_name(path.name)
    stat = path.stat()
    return {
        "filename": path.name,
        "character_id": parsed.character_id,
        "generation": parsed.generation,
        "size_bytes": stat.st_size,
        "sha256": template_sha256(path),
        "registered_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "active": active,
        "representative": representative,
    }


def move_to_quarantine(upload_root: Path, character_id: int, filename: str) -> tuple[Path, Path]:
    active_root = upload_root / "templates"
    quarantine_root = upload_root / "template_quarantine"
    source = safe_template_path(active_root, filename, character_id)
    if not source.is_file():
        raise FileNotFoundError(filename)
    quarantine_root.mkdir(parents=True, exist_ok=True)
    destination = safe_template_path(quarantine_root, filename, character_id)
    if destination.exists():
        raise FileExistsError(filename)
    os.replace(source, destination)
    return source, destination


def restore_from_quarantine(upload_root: Path, character_id: int, filename: str) -> tuple[Path, Path]:
    active_root = upload_root / "templates"
    quarantine_root = upload_root / "template_quarantine"
    source = safe_template_path(quarantine_root, filename, character_id)
    if not source.is_file():
        raise FileNotFoundError(filename)
    active_root.mkdir(parents=True, exist_ok=True)
    destination = safe_template_path(active_root, filename, character_id)
    if destination.exists():
        destination = safe_template_path(active_root, next_template_name(active_root, character_id), character_id)
    os.replace(source, destination)
    return source, destination


def reassign_active_template(
    upload_root: Path, source_character_id: int, target_character_id: int, filename: str
) -> tuple[Path, Path, bool]:
    """Move an active file, avoiding duplicate content in the target Character."""
    active_root = upload_root / "templates"
    quarantine_root = upload_root / "template_quarantine"
    source = safe_template_path(active_root, filename, source_character_id)
    if not source.is_file():
        raise FileNotFoundError(filename)
    digest = template_sha256(source)
    duplicate = next(
        (
            path for path in list_template_paths(active_root)
            if parse_template_name(path.name).character_id == target_character_id
            and template_sha256(path) == digest
        ),
        None,
    )
    if duplicate is not None:
        quarantine_root.mkdir(parents=True, exist_ok=True)
        destination = safe_template_path(quarantine_root, filename, source_character_id)
        if destination.exists():
            destination = safe_template_path(
                quarantine_root, next_template_name(quarantine_root, source_character_id), source_character_id
            )
        os.replace(source, destination)
        return source, destination, True
    destination = safe_template_path(
        active_root, next_template_name(active_root, target_character_id), target_character_id
    )
    os.replace(source, destination)
    return source, destination, False


def rollback_move(current: Path, original: Path) -> None:
    if current.exists() and not original.exists():
        original.parent.mkdir(parents=True, exist_ok=True)
        os.replace(current, original)
