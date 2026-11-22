"""Track when an article image lost its last saved reference."""

from alembic import op
import sqlalchemy as sa


revision = "9465f112c8ab"
down_revision = "562ed09f11ae"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "article_image_lifecycle",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("unreferenced_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_article_image_lifecycle_unreferenced_since", "article_image_lifecycle", ["unreferenced_since"])


def downgrade():
    op.drop_index("ix_article_image_lifecycle_unreferenced_since", table_name="article_image_lifecycle")
    op.drop_table("article_image_lifecycle")
