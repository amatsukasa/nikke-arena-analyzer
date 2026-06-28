from pathlib import Path


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
