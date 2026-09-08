"""add champion arena master fields

Revision ID: a8d4c2e6f901
Revises: f7c9d2e4a6b8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a8d4c2e6f901"
down_revision: Union[str, Sequence[str], None] = "f7c9d2e4a6b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.add_column(sa.Column("game_start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("display_order", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("is_champion_arena", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("has_match_data", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.drop_column("has_match_data")
        batch_op.drop_column("is_champion_arena")
        batch_op.drop_column("display_order")
        batch_op.drop_column("game_start_date")
