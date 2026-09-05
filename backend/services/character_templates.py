from pathlib import Path

from services.template_management import list_template_paths, parse_template_name, representative_template


def get_character_template_inventory(upload_dir: str | Path) -> dict[int, Path]:
    """Return the latest active generation per Character without changing metadata."""
    template_dir = Path(upload_dir) / "templates"
    character_ids = {parse_template_name(path.name).character_id for path in list_template_paths(template_dir)}
    return {
        character_id: path
        for character_id in character_ids
        if (path := representative_template(template_dir, character_id)) is not None
    }


def find_character_template(upload_dir: str | Path, char_id: int) -> Path | None:
    return representative_template(Path(upload_dir) / "templates", char_id)
