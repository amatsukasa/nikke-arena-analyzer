"""Track article image grace periods and serialize reference changes with cleanup."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import logging
from threading import Lock
from uuid import UUID

from sqlalchemy import select, text

import models
from services import article_images


GRACE_PERIOD = timedelta(days=7)
# Shared by all workers connected to the same PostgreSQL database and uploads volume.
LOCK_KEY = 0x415254494D414745
_sqlite_lock = Lock()
logger = logging.getLogger(__name__)


@contextmanager
def image_transaction(db):
    """Hold the lock through commit or rollback, including any file operations."""
    if db.get_bind().dialect.name == "sqlite":
        # SQLite is used by the in-process test clients.
        with _sqlite_lock:
            try:
                yield
            finally:
                db.rollback()
    else:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        try:
            yield
        finally:
            db.rollback()


def version_images(*versions):
    ids = set()
    nodes = [version["body"] for version in versions if version]
    while nodes:
        node = nodes.pop()
        if node["type"] == "articleImage":
            ids.add(UUID(node["attrs"]["imageId"]))
        nodes.extend(node.get("content") or ())
    return ids


def referenced_images(db):
    ids = set()
    for draft, published in db.execute(select(models.Article.draft, models.Article.published)):
        ids.update(version_images(draft, published))
    return ids


def track(db, image_ids, unreferenced_since):
    if not image_ids:
        return
    image_model = models.ArticleImageLifecycle
    existing = {row.id: row for row in db.scalars(select(image_model).where(image_model.id.in_(image_ids)))}
    for image_id in image_ids:
        if image_id in existing:
            existing[image_id].unreferenced_since = unreferenced_since
        else:
            db.add(image_model(id=image_id, unreferenced_since=unreferenced_since))


def update_references(db, article, previous):
    current = version_images(article.draft, article.published)
    track(db, current - previous, None)
    removed = previous - current
    if removed:
        db.flush()
        track(db, removed - referenced_images(db), datetime.now(timezone.utc))


def managed_files(root):
    for path in root.iterdir():
        if path.suffix != ".webp" or path.is_symlink() or not path.is_file():
            continue
        try:
            image_id = UUID(path.stem)
        except ValueError:
            continue
        if str(image_id) == path.stem:
            yield image_id


def collect_unused(db, *, now=None):
    """Collect expired images and discover files left by older application versions."""
    root = article_images.ARTICLE_IMAGE_ROOT
    if not root.is_dir() or root.is_symlink():
        return
    image_model = models.ArticleImageLifecycle
    with image_transaction(db):
        now = now or datetime.now(timezone.utc)
        tracked = set(db.scalars(select(image_model.id)))
        unknown = set(managed_files(root)) - tracked
        due = list(db.scalars(select(image_model).where(
            image_model.unreferenced_since <= now - GRACE_PERIOD,
        )))
        if unknown or due:
            # Recheck both durable versions while writers and other collectors are excluded.
            referenced = referenced_images(db)
            track(db, unknown & referenced, None)
            track(db, unknown - referenced, now)
            for row in due:
                if row.id in referenced:
                    row.unreferenced_since = None
                    continue
                path = article_images.image_path(row.id)
                if path.is_symlink():
                    continue
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove unused article image %s", row.id, exc_info=True)
                else:
                    db.delete(row)
        db.commit()
