"""Store the administrator-selected debut roster on each championship."""

from alembic import op
import sqlalchemy as sa


revision = "562ed09f11ae"
down_revision = "314eefc439a1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("championships", sa.Column(
        "debut_character_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'"),
    ))


def downgrade():
    op.drop_column("championships", "debut_character_ids")
