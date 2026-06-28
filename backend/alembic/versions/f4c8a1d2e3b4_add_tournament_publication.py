"""add tournament publication state

Revision ID: f4c8a1d2e3b4
Revises: 8cd9e0f1a3b4
Create Date: 2026-06-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f4c8a1d2e3b4"
down_revision: Union[str, Sequence[str], None] = "8cd9e0f1a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("tournaments")}

    if "publication_status" not in columns:
        op.add_column(
            "tournaments",
            sa.Column(
                "publication_status",
                sa.String(),
                nullable=False,
                server_default="published",
            ),
        )
    if "published_at" not in columns:
        op.add_column(
            "tournaments",
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "published_by" not in columns:
        op.add_column(
            "tournaments",
            sa.Column("published_by", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_tournaments_published_by_app_users",
            "tournaments",
            "app_users",
            ["published_by"],
            ["id"],
        )

    # 既存大会は現在の公開状態を維持する。
    op.execute(
        "UPDATE tournaments "
        "SET publication_status = 'published', "
        "published_at = COALESCE(published_at, created_at, CURRENT_TIMESTAMP)"
    )
    op.alter_column(
        "tournaments",
        "publication_status",
        existing_type=sa.String(),
        server_default="draft",
        nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys("tournaments")
    }
    if "fk_tournaments_published_by_app_users" in foreign_keys:
        op.drop_constraint(
            "fk_tournaments_published_by_app_users",
            "tournaments",
            type_="foreignkey",
        )

    columns = {column["name"] for column in inspector.get_columns("tournaments")}
    if "published_by" in columns:
        op.drop_column("tournaments", "published_by")
    if "published_at" in columns:
        op.drop_column("tournaments", "published_at")
    if "publication_status" in columns:
        op.drop_column("tournaments", "publication_status")
