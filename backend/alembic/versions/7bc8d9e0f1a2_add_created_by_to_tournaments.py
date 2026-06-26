"""add created_by to tournaments

Revision ID: 7bc8d9e0f1a2
Revises: 3ab7c28bf9e0
Create Date: 2026-06-26 20:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = '7bc8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = '3ab7c28bf9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    # tournaments テーブルに created_by カラムを追加（存在しない場合のみ）
    columns = [col['name'] for col in inspector.get_columns('tournaments')]
    if 'created_by' not in columns:
        op.add_column('tournaments', sa.Column('created_by', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_tournaments_created_by', 'tournaments', 'users', ['created_by'], ['id'])
        print("[Migration] tournamentsテーブルにcreated_byカラムを追加しました。")
    else:
        print("[Migration] tournaments.created_byカラムはすでに存在するため、追加をスキップします。")


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    columns = [col['name'] for col in inspector.get_columns('tournaments')]
    if 'created_by' in columns:
        op.drop_constraint('fk_tournaments_created_by', 'tournaments', type_='foreignkey')
        op.drop_column('tournaments', 'created_by')
