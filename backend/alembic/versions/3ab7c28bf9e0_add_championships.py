"""add championships

Revision ID: 3ab7c28bf9e0
Revises: e8950d0bb43e
Create Date: 2026-06-26 19:47:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = '3ab7c28bf9e0'
down_revision: Union[str, Sequence[str], None] = 'e8950d0bb43e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()
    
    # 1. championships テーブルの作成（存在しない場合のみ）
    if 'championships' not in tables:
        op.create_table('championships',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('date', sa.Date(), nullable=False),
            sa.Column('start_date', sa.Date(), nullable=False),
            sa.Column('owner_name', sa.String(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_championships_id'), 'championships', ['id'], unique=False)
        print("[Migration] championshipsテーブルを作成しました。")
    else:
        print("[Migration] championshipsテーブルはすでに存在するため、作成をスキップします。")
        
    # 2. tournaments テーブルに championship_id カラムを追加（存在しない場合のみ）
    columns = [col['name'] for col in inspector.get_columns('tournaments')]
    if 'championship_id' not in columns:
        op.add_column('tournaments', sa.Column('championship_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_tournaments_championship_id', 'tournaments', 'championships', ['championship_id'], ['id'])
        print("[Migration] tournamentsテーブルにchampionship_idカラムを追加しました。")
    else:
        print("[Migration] tournaments.championship_idカラムはすでに存在するため、追加をスキップします。")


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()
    
    if 'tournaments' in tables:
        columns = [col['name'] for col in inspector.get_columns('tournaments')]
        if 'championship_id' in columns:
            op.drop_constraint('fk_tournaments_championship_id', 'tournaments', type_='foreignkey')
            op.drop_column('tournaments', 'championship_id')
            
    if 'championships' in tables:
        op.drop_index(op.f('ix_championships_id'), table_name='championships')
        op.drop_table('championships')
