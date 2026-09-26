"""add character arena relevance flag

Revision ID: b9e5d3f7a012
Revises: a8d4c2e6f901
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9e5d3f7a012"
down_revision: Union[str, Sequence[str], None] = "a8d4c2e6f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("characters") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_arena_relevant",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_column("is_arena_relevant")
