"""add staff approval state

Revision ID: d3a8e5f7b9c1
Revises: f4c8a1d2e3b4
Create Date: 2026-06-28 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "d3a8e5f7b9c1"
down_revision: Union[str, Sequence[str], None] = "f4c8a1d2e3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("app_users")}
    additions = [
        ("approval_status", sa.String(), False, "active"),
        ("approval_token_hash", sa.String(), True, None),
        ("approval_requested_at", sa.DateTime(timezone=True), True, None),
        ("approved_at", sa.DateTime(timezone=True), True, None),
        ("approved_by", sa.Integer(), True, None),
    ]
    for name, column_type, nullable, default in additions:
        if name not in columns:
            op.add_column(
                "app_users",
                sa.Column(
                    name,
                    column_type,
                    nullable=nullable,
                    server_default=default,
                ),
            )
    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in inspect(op.get_bind()).get_foreign_keys("app_users")
    }
    if "fk_app_users_approved_by_app_users" not in foreign_keys:
        op.create_foreign_key(
            "fk_app_users_approved_by_app_users",
            "app_users",
            "app_users",
            ["approved_by"],
            ["id"],
        )
    op.execute("UPDATE app_users SET approval_status = 'active'")
    op.alter_column(
        "app_users",
        "approval_status",
        existing_type=sa.String(),
        server_default="pending",
        nullable=False,
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys("app_users")
    }
    if "fk_app_users_approved_by_app_users" in foreign_keys:
        op.drop_constraint(
            "fk_app_users_approved_by_app_users",
            "app_users",
            type_="foreignkey",
        )
    columns = {column["name"] for column in inspector.get_columns("app_users")}
    for name in [
        "approved_by",
        "approved_at",
        "approval_requested_at",
        "approval_token_hash",
        "approval_status",
    ]:
        if name in columns:
            op.drop_column("app_users", name)
