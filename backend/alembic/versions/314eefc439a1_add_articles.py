"""Add drafts, publication snapshots, and public image references."""

from alembic import op
import sqlalchemy as sa


revision = "314eefc439a1"
down_revision = "6e41b7ad2c90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "articles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("published", sa.JSON(), nullable=True),
        sa.Column("published_kind", sa.String(20), nullable=True),
        sa.Column(
            "published_championship_id", sa.Integer(),
            sa.ForeignKey("championships.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_articles_public_listing", "articles", [
        "published_kind", "published_championship_id", "published_at",
    ])
    op.create_table(
        "article_public_images",
        sa.Column("article_id", sa.Uuid(), sa.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("image_id", sa.Uuid(), primary_key=True),
    )
    op.create_index("ix_article_public_images_image_id", "article_public_images", ["image_id"])


def downgrade():
    op.drop_table("article_public_images")
    op.drop_table("articles")
