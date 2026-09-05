"""add character template reviews

Revision ID: f7c9d2e4a6b8
Revises: e6b8c1d2f3a4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7c9d2e4a6b8"
down_revision: Union[str, Sequence[str], None] = "e6b8c1d2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "character_template_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("predicted_character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("corrected_character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("matched_template_filename", sa.String(), nullable=False),
        sa.Column("corrected_template_filename", sa.String(), nullable=True),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=True),
        sa.Column("seed_number", sa.Integer(), nullable=True),
        sa.Column("champion_slot", sa.SmallInteger(), nullable=True),
        sa.Column("round_number", sa.SmallInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("analysis_token", sa.String(), nullable=False),
        sa.Column("match_method", sa.String(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'kept', 'reassigned', 'disabled')", name="ck_template_review_status"),
        sa.UniqueConstraint("analysis_token", "round_number", "position", "matched_template_filename", name="uq_template_review_analysis_position_match"),
    )
    op.create_table(
        "character_template_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("source_character_id", sa.Integer(), nullable=True),
        sa.Column("target_character_id", sa.Integer(), nullable=True),
        sa.Column("source_filename", sa.String(), nullable=True),
        sa.Column("target_filename", sa.String(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=True),
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("character_template_reviews.id"), nullable=True),
        sa.Column("success", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("character_template_audits")
    op.drop_table("character_template_reviews")
