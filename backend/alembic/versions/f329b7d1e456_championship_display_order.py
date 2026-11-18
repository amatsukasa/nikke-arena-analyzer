"""Title-level ordering; preserve all legacy tournament metadata."""
from alembic import op
import sqlalchemy as sa
import json
revision = "f329b7d1e456"
down_revision = "e218a6c0d345"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if "display_order" not in {column["name"] for column in sa.inspect(bind).get_columns("championships")}:
        op.add_column("championships", sa.Column("display_order", sa.Integer(), nullable=True))
    report = {"adopted": [], "conflicts": [], "unchanged": []}
    for title in bind.execute(sa.text("SELECT id, display_order FROM championships ORDER BY id")).mappings().all():
        rows = bind.execute(sa.text("SELECT id, display_order FROM tournaments WHERE championship_id=:id ORDER BY id"), {"id": title["id"]}).mappings().all()
        observed = {row["display_order"] for row in rows}
        if title["display_order"] is None and len(observed) == 1 and None not in observed:
            bind.execute(sa.text("UPDATE championships SET display_order=:value WHERE id=:id AND display_order IS NULL"), {"value": next(iter(observed)), "id": title["id"]})
            report["adopted"].append(title["id"])
        elif title["display_order"] is None and len(observed) > 1:
            report["conflicts"].append({"championship_id": title["id"], "tournaments": [dict(row) for row in rows]})
        else:
            report["unchanged"].append(title["id"])
    print("[Title order migration] " + json.dumps(report, sort_keys=True))

def downgrade():
    raise RuntimeError("Export title order settings before downgrade")
