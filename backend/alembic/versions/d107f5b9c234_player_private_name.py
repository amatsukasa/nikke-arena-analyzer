"""Add private player names without modifying public names."""
from alembic import op
import sqlalchemy as sa
revision = "d107f5b9c234"
down_revision = "c0f6e4a8b123"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("players", sa.Column("private_name", sa.String(50), nullable=True))

def downgrade():
    op.drop_column("players", "private_name")
