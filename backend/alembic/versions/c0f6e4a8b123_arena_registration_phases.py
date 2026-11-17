"""Add immutable arena phase registrations and results. No existing rows are changed."""
from alembic import op
import sqlalchemy as sa

revision = "c0f6e4a8b123"
down_revision = "b9e5d3f7a012"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tournaments") as batch:
        batch.add_column(sa.Column("deck_registration_phases", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("arena_deck_registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("qualification", sa.String(64), nullable=False),
        sa.Column("teams", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("phase IN ('initial', 'best8', 'final')", name="ck_arena_registration_phase"))
    op.create_index("ix_arena_deck_registrations_tournament_id", "arena_deck_registrations", ["tournament_id"])
    op.create_index("ix_arena_deck_registrations_player_id", "arena_deck_registrations", ["player_id"])
    op.create_table("arena_match_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id"), nullable=False),
        sa.Column("match_key", sa.String(32), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("upstream", sa.String(64), nullable=False),
        sa.Column("attacker_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("defender_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("winner_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("attacker_registration_id", sa.Integer(), sa.ForeignKey("arena_deck_registrations.id")),
        sa.Column("defender_registration_id", sa.Integer(), sa.ForeignKey("arena_deck_registrations.id")),
        sa.Column("attacker_teams", sa.JSON(), nullable=False),
        sa.Column("defender_teams", sa.JSON(), nullable=False),
        sa.Column("rounds", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("phase IN ('initial', 'best8', 'final')", name="ck_arena_match_phase"))
    op.create_index("ix_arena_match_revisions_tournament_id", "arena_match_revisions", ["tournament_id"])


def downgrade():
    # A downgrade would discard historical registrations/results. Require an explicit recovery plan.
    raise RuntimeError("Arena phase history must be exported and reviewed before schema downgrade")
