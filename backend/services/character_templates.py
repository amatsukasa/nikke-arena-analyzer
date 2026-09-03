from pathlib import Path
import re


_TEMPLATE_NAME_PATTERN = re.compile(r"^char_(\d+)(?:_.*)?\.png$")


def get_character_template_inventory(upload_dir: str | Path) -> dict[int, Path]:
    """Return one existing template per Character without changing DB metadata."""
    template_dir = Path(upload_dir) / "templates"
    if not template_dir.is_dir():
        return {}

    inventory: dict[int, Path] = {}
    for path in sorted(template_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        match = _TEMPLATE_NAME_PATTERN.fullmatch(path.name)
        if not match:
            continue
        char_id = int(match.group(1))
        current = inventory.get(char_id)
        # Keep find_character_template()'s legacy-file preference.
        if current is None or path.name == f"char_{char_id}.png":
            inventory[char_id] = path
    return inventory


def find_character_template(upload_dir: str | Path, char_id: int) -> Path | None:
    template_dir = Path(upload_dir) / "templates"
    legacy_path = template_dir / f"char_{char_id}.png"
    if legacy_path.is_file():
        return legacy_path
    if not template_dir.is_dir():
        return None
    candidates = sorted(
        path
        for path in template_dir.glob(f"char_{char_id}_*.png")
        if path.is_file()
    )
    return candidates[0] if candidates else None
