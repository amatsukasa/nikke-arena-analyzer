"""add app_users table

Revision ID: a1b2c3d4e5f6
Revises: 39a682ac2a94
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "39a682ac2a94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("is_banned", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_app_users_email"), "app_users", ["email"], unique=True)
    op.create_index(op.f("ix_app_users_id"), "app_users", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_app_users_id"), table_name="app_users")
    op.drop_index(op.f("ix_app_users_email"), table_name="app_users")
    op.drop_table("app_users")