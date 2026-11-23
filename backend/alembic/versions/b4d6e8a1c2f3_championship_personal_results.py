"""Configure personal results independently of published tournament analysis."""

from alembic import op
import sqlalchemy as sa


revision = "b4d6e8a1c2f3"
down_revision = "9465f112c8ab"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("championships", sa.Column("arena_results_enabled", sa.Boolean(), nullable=True))
    op.create_table(
        "arena_result_legacy_links",
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("championship_id", sa.Integer(), sa.ForeignKey("championships.id", ondelete="RESTRICT"), nullable=False),
    )
    op.create_index("ix_arena_result_legacy_links_championship_id", "arena_result_legacy_links", ["championship_id"])


def downgrade():
    op.drop_table("arena_result_legacy_links")
    op.drop_column("championships", "arena_results_enabled")
