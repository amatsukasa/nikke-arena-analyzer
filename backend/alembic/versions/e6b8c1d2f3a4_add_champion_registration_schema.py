"""add champion registration schema

Revision ID: e6b8c1d2f3a4
Revises: c2f7a9b4d6e8
Create Date: 2026-08-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6b8c1d2f3a4"
down_revision: Union[str, Sequence[str], None] = "c2f7a9b4d6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.add_column(sa.Column(
            "registration_scope",
            sa.String(),
            nullable=False,
            server_default=sa.text("'full_64'"),
        ))
        batch_op.add_column(sa.Column(
            "provider_game_start_date",
            sa.Date(),
            nullable=True,
        ))
        batch_op.create_check_constraint(
            "ck_tournament_registration_scope",
            "registration_scope IN ('full_64', 'champion_8')",
        )

    # Snapshot the creator profile value. Missing creators and missing profile
    # dates intentionally remain NULL.
    op.execute(sa.text("""
        UPDATE tournaments
        SET provider_game_start_date = (
            SELECT app_users.game_start_date
            FROM app_users
            WHERE app_users.id = tournaments.created_by
        )
        WHERE tournaments.created_by IS NOT NULL
    """))

    with op.batch_alter_table("players") as batch_op:
        batch_op.add_column(sa.Column("champion_slot", sa.SmallInteger(), nullable=True))
        batch_op.create_check_constraint(
            "ck_player_champion_slot_range",
            "champion_slot IS NULL OR (champion_slot >= 1 AND champion_slot <= 8)",
        )
        batch_op.create_unique_constraint(
            "uq_player_tournament_champion_slot",
            ["tournament_id", "champion_slot"],
        )

    with op.batch_alter_table("matches") as batch_op:
        batch_op.add_column(sa.Column("bracket_stage", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("bracket_slot", sa.SmallInteger(), nullable=True))
        batch_op.create_check_constraint(
            "ck_match_bracket_stage",
            "bracket_stage IS NULL OR bracket_stage IN ('quarterfinal', 'semifinal', 'final')",
        )
        batch_op.create_unique_constraint(
            "uq_match_tournament_bracket_slot",
            ["tournament_id", "bracket_stage", "bracket_slot"],
        )


def downgrade() -> None:
    with op.batch_alter_table("matches") as batch_op:
        batch_op.drop_constraint("uq_match_tournament_bracket_slot", type_="unique")
        batch_op.drop_constraint("ck_match_bracket_stage", type_="check")
        batch_op.drop_column("bracket_slot")
        batch_op.drop_column("bracket_stage")

    with op.batch_alter_table("players") as batch_op:
        batch_op.drop_constraint("uq_player_tournament_champion_slot", type_="unique")
        batch_op.drop_constraint("ck_player_champion_slot_range", type_="check")
        batch_op.drop_column("champion_slot")

    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.drop_constraint("ck_tournament_registration_scope", type_="check")
        batch_op.drop_column("provider_game_start_date")
        batch_op.drop_column("registration_scope")
