"""update user and championship

Revision ID: 8cd9e0f1a3b4
Revises: 7bc8d9e0f1a2
Create Date: 2026-06-26 20:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = '8cd9e0f1a3b4'
down_revision: Union[str, Sequence[str], None] = '7bc8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    # 1. app_users に provider_name, game_start_date カラムを追加（存在しない場合のみ）
    columns = [col['name'] for col in inspector.get_columns('app_users')]
    if 'provider_name' not in columns:
        op.add_column('app_users', sa.Column('provider_name', sa.String(), nullable=True))
        print("[Migration] app_usersテーブルにprovider_nameカラムを追加しました。")
    if 'game_start_date' not in columns:
        op.add_column('app_users', sa.Column('game_start_date', sa.Date(), nullable=True))
        print("[Migration] app_usersテーブルにgame_start_dateカラムを追加しました。")

    # 2. championships テーブルの date, start_date を nullable に変更する
    # SQLiteなどALTER COLUMNが制限される環境で動作するように op.alter_column を安全にコールする
    try:
        op.alter_column('championships', 'date', existing_type=sa.Date(), nullable=True)
        op.alter_column('championships', 'start_date', existing_type=sa.Date(), nullable=True)
        print("[Migration] championshipsテーブルのdate, start_dateカラムをnullable=Trueに変更しました。")
    except Exception as e:
        print(f"[Migration] championshipsテーブルのカラム属性変更時にエラーが発生しました (無視可能): {e}")


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    # 1. app_users からカラム削除
    columns = [col['name'] for col in inspector.get_columns('app_users')]
    if 'provider_name' in columns:
        op.drop_column('app_users', 'provider_name')
    if 'game_start_date' in columns:
        op.drop_column('app_users', 'game_start_date')

    # 2. championships テーブルの date, start_date を NOT NULL に戻す（必要に応じて）
    try:
        op.alter_column('championships', 'date', existing_type=sa.Date(), nullable=False)
        op.alter_column('championships', 'start_date', existing_type=sa.Date(), nullable=False)
    except Exception as e:
        print(f"[Migration] championshipsテーブルのロールバック時にエラーが発生しました: {e}")
