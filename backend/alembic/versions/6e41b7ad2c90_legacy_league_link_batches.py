"""Store approved legacy league links separately from the source matches."""

import sqlalchemy as sa
from alembic import op

revision = "6e41b7ad2c90"
down_revision = "f329b7d1e456"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "arena_legacy_league_link_batches",
        sa.Column("id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("operator", sa.String(120), nullable=False),
        sa.Column("links", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("arena_legacy_league_link_batches")
