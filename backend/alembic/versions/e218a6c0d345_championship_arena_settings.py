"""Idempotently add title settings; adopt only unanimous, non-null legacy values."""
from collections import defaultdict
import json
from alembic import op
import sqlalchemy as sa

revision = "e218a6c0d345"
down_revision = "d107f5b9c234"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    mapping = {"deck_registration_phases": "deck_registration_phases", "is_champion_arena": "is_champion_arena", "include_in_statistics": "has_match_data"}
    columns = {column["name"] for column in sa.inspect(bind).get_columns("championships")}
    for name in mapping:
        if name not in columns:
            op.add_column("championships", sa.Column(name, sa.Boolean(), nullable=True))
    grouped = defaultdict(list)
    for row in bind.execute(sa.text("SELECT id, championship_id, deck_registration_phases, is_champion_arena, has_match_data FROM tournaments ORDER BY id")).mappings():
        grouped[row["championship_id"]].append(row)
    counts = {"titles": 0, "fields_adopted": 0, "already_configured_fields": 0, "unlinked_tournaments": len(grouped.get(None, [])), "conflicts": [], "no_linked_data": []}
    before_nulls = {name: bind.execute(sa.text(f"SELECT count(*) FROM championships WHERE {name} IS NULL")).scalar() for name in mapping}
    print("[Title settings migration before] " + json.dumps({"titles": bind.execute(sa.text("SELECT count(*) FROM championships")).scalar(), "unconfigured_fields": before_nulls, "unlinked_tournaments": len(grouped.get(None, []))}, sort_keys=True))
    for title in bind.execute(sa.text("SELECT id, deck_registration_phases, is_champion_arena, include_in_statistics FROM championships ORDER BY id")).mappings().all():
        counts["titles"] += 1
        rows = grouped.get(title["id"], [])
        if not rows:
            counts["no_linked_data"].append(title["id"])
        for target, source in mapping.items():
            if title[target] is not None:
                counts["already_configured_fields"] += 1
                continue
            observed = {row[source] for row in rows}
            if rows and len(observed) == 1 and None not in observed:
                result = bind.execute(sa.text(f"UPDATE championships SET {target}=:value WHERE id=:id AND {target} IS NULL"), {"value": next(iter(observed)), "id": title["id"]})
                counts["fields_adopted"] += result.rowcount
            elif rows:
                counts["conflicts"].append({"championship_id": title["id"], "field": target, "tournaments": [{"id": row["id"], "value": row[source]} for row in rows]})
    after_nulls = {name: bind.execute(sa.text(f"SELECT count(*) FROM championships WHERE {name} IS NULL")).scalar() for name in mapping}
    print("[Title settings migration] " + json.dumps({**counts, "before_unconfigured": before_nulls, "after_unconfigured": after_nulls}, sort_keys=True))


def downgrade():
    raise RuntimeError("Title settings and legacy history must be exported before downgrade")
