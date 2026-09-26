"""add representative template filename

Revision ID: c4d8e2f6a901
Revises: b9e5d3f7a012
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d8e2f6a901"
down_revision: Union[str, Sequence[str], None] = "b9e5d3f7a012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("representative_template_filename", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("characters", "representative_template_filename")
