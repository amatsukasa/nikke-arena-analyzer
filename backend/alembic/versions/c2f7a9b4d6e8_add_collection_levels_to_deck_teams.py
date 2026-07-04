"""add collection levels to deck teams

Revision ID: c2f7a9b4d6e8
Revises: 7e2667a37d93
Create Date: 2026-07-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "c2f7a9b4d6e8"
down_revision: Union[str, Sequence[str], None] = "7e2667a37d93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("deck_teams")}
    for slot in range(1, 6):
        column_name = f"collection{slot}"
        if column_name not in columns:
            op.add_column(
                "deck_teams",
                sa.Column(column_name, sa.String(), nullable=True),
            )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("deck_teams")}
    for slot in range(5, 0, -1):
        column_name = f"collection{slot}"
        if column_name in columns:
            op.drop_column("deck_teams", column_name)
