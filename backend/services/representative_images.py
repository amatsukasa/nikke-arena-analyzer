from __future__ import annotations

from pathlib import Path

import models
from services.template_management import parse_template_name


def initialize_representative_templates(db, upload_dir: str | Path, *, apply: bool = False) -> dict:
    """Select the oldest surviving active generation for currently unset Characters."""
    template_root = Path(upload_dir) / "templates"
    candidates: dict[int, dict[int, list[str]]] = {}
    invalid_files: list[str] = []

    if template_root.is_dir():
        for path in template_root.iterdir():
            if not path.is_file() or path.is_symlink():
                if path.is_symlink():
                    invalid_files.append(path.name)
                continue
            try:
                parsed = parse_template_name(path.name)
            except ValueError:
                invalid_files.append(path.name)
                continue
            candidates.setdefault(parsed.character_id, {}).setdefault(
                parsed.generation, []
            ).append(path.name)

    targets = db.query(models.Character).filter(
        models.Character.representative_template_filename.is_(None)
    ).order_by(models.Character.id).all()
    known_ids = {character.id for character in db.query(models.Character.id).all()}
    report = {
        "apply": apply,
        "target_characters": len(targets),
        "selected_count": 0,
        "updated_count": 0,
        "unset_count": 0,
        "invalid_files": sorted(invalid_files),
        "no_candidate": [],
        "ambiguous_generation": [],
        "unknown_character_files": sorted(
            filename
            for character_id, generations in candidates.items()
            if character_id not in known_ids
            for filenames in generations.values()
            for filename in filenames
        ),
        "selected": [],
    }

    for character in targets:
        generations = candidates.get(character.id)
        if not generations:
            report["no_candidate"].append(character.id)
            continue
        oldest_generation = min(generations)
        filenames = sorted(generations[oldest_generation])
        if len(filenames) != 1:
            report["ambiguous_generation"].append({
                "character_id": character.id,
                "generation": oldest_generation,
                "filenames": filenames,
            })
            continue
        filename = filenames[0]
        report["selected"].append({
            "character_id": character.id,
            "filename": filename,
            "generation": oldest_generation,
        })
        if apply:
            character.representative_template_filename = filename
            report["updated_count"] += 1
        report["selected_count"] += 1

    report["unset_count"] = len(targets) - report["selected_count"]
    return report
