from pathlib import Path

from services.template_management import list_template_paths, parse_template_name, representative_template


def get_character_template_inventory(upload_dir: str | Path) -> dict[int, Path]:
    """Return the latest active generation per Character without changing metadata."""
    template_dir = Path(upload_dir) / "templates"
    inventory: dict[int, Path] = {}
    generations: dict[int, int] = {}
    for path in list_template_paths(template_dir):
        parsed = parse_template_name(path.name)
        if parsed.generation > generations.get(parsed.character_id, -1):
            inventory[parsed.character_id] = path
            generations[parsed.character_id] = parsed.generation
    return inventory


def find_character_template(upload_dir: str | Path, char_id: int) -> Path | None:
    return representative_template(Path(upload_dir) / "templates", char_id)
