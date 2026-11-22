"""Exercise the article routes with separate admin, provider and public clients."""

import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import create_access_token
from database import Base, get_db
from main import app, periodic_upload_cleanup
from models import AppUser, ArticleImageLifecycle, Championship, Character
from services import article_image_cleanup, article_images


ARTICLE_URL = "/api/articles"
ADMIN_URL = "/api/admin/articles"
DETAILS_URL = "/?tab=matchups&teamKey=1-2-3-4-5&detail_phase=final&tournaments=206"


def draft(title="Season 1", *, kind="season", championship=1, characters=(), image=None):
    content = [{
        "type": "paragraph",
        "content": [{"type": "text", "text": "Match results", "marks": [
            {"type": "link", "attrs": {"href": DETAILS_URL, "target": "_blank"}},
            {"type": "bold"},
        ]}],
    }]
    if image:
        content.append({"type": "articleImage", "attrs": {"imageId": image, "caption": "Round results"}})
    return {
        "kind": kind, "championship_id": championship, "character_ids": list(characters),
        "title": title, "body": {"type": "doc", "content": content},
    }


def get_png():
    output = BytesIO()
    Image.new("RGB", (2800, 1400), (35, 80, 160)).save(output, "PNG")
    return output.getvalue()


class ArticlePublicationTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        session = self.session = sessionmaker(bind=engine, autoflush=False)

        with session.begin() as db:
            db.add_all([
                AppUser(id=1, email="admin@test.invalid", hashed_password="unused", role="admin", approval_status="active"),
                AppUser(id=2, email="provider@test.invalid", hashed_password="unused", role="contributor", approval_status="active"),
                Championship(id=1, name="Season 1"),
                Championship(id=2, name="Season 2"),
                Character(id=90, name="サクラ"),
            ])

        def test_db():
            with session() as db:
                yield db

        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        self.enterContext(patch("services.article_images.ARTICLE_IMAGE_ROOT", self.root))
        self.enterContext(patch.dict(app.dependency_overrides, {get_db: test_db}))
        self.reader = TestClient(app)
        self.admin = TestClient(app, headers={"Authorization": f"Bearer {create_access_token({'sub': '1'})}"})
        self.provider = TestClient(app, headers={"Authorization": f"Bearer {create_access_token({'sub': '2'})}"})
        for client in (self.reader, self.admin, self.provider):
            self.addCleanup(client.close)

    def upload(self):
        response = self.admin.post(f"{ADMIN_URL}/images", files={"file": ("screenshot.png", get_png(), "image/png")})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["image_id"]

    def create(self, body, publish=False):
        response = self.admin.post(ADMIN_URL, json={"draft": body, "publish": publish})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def save(self, article, body, publish=False):
        response = self.admin.put(f"{ADMIN_URL}/{article['id']}", json={
            "draft": body, "publish": publish, "revision": article["revision"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_preview_images_and_drafts_are_private_until_each_publication(self):
        first = self.upload()
        first_image = f"{ARTICLE_URL}/images/{first}"
        article = self.create(draft(image=first))
        path = f"{ARTICLE_URL}/{article['id']}"
        self.assertEqual(self.reader.get(path).status_code, 404)
        self.assertEqual(self.reader.get(first_image).status_code, 404)
        self.assertEqual(self.provider.get(first_image).status_code, 404)
        self.assertEqual(self.reader.get(f"{ARTICLE_URL}/season/1").json(), {"latest": None, "earlier": []})
        editor = self.admin.get(f"{ADMIN_URL}/{article['id']}").json()
        self.assertEqual(editor["draft"]["body"]["content"][1]["attrs"]["caption"], "Round results")
        marks = editor["draft"]["body"]["content"][0]["content"][0]["marks"]
        self.assertEqual(marks[0]["attrs"], {"href": DETAILS_URL})
        image_response = self.admin.get(first_image)
        self.assertEqual(image_response.headers["content-type"], "image/webp")
        with Image.open(BytesIO(image_response.content)) as image:
            self.assertEqual(image.size, (2400, 1200))

        published = self.save(article, editor["draft"], publish=True)
        old_public = self.reader.get(path).json()
        self.assertEqual(self.reader.get(first_image).status_code, 200)
        self.assertEqual(old_public["published_at"], old_public["updated_at"])
        self.assertFalse(published["has_unpublished_changes"])

        replacement = self.upload()
        replacement_path = f"{ARTICLE_URL}/images/{replacement}"
        revised_body = draft("Corrected title", image=replacement)
        saved = self.save(published, revised_body)
        self.assertTrue(saved["has_unpublished_changes"])
        self.assertEqual(self.reader.get(path).json(), old_public)
        self.assertEqual(self.reader.get(first_image).status_code, 200)
        self.assertEqual(self.reader.get(replacement_path).status_code, 404)
        stale = self.admin.put(f"{ADMIN_URL}/{article['id']}", json={
            "draft": revised_body, "revision": published["revision"], "publish": True,
        })
        self.assertEqual(stale.status_code, 409)

        updated = self.save(saved, revised_body, publish=True)
        current = self.reader.get(path).json()
        self.assertEqual(current["id"], article["id"])
        self.assertEqual(current["title"], "Corrected title")
        self.assertEqual(current["published_at"], old_public["published_at"])
        self.assertGreater(current["updated_at"], old_public["updated_at"])
        self.save(updated, revised_body, publish=True)
        self.assertEqual(self.reader.get(path).json()["updated_at"], current["updated_at"])
        self.assertEqual(self.reader.get(first_image).status_code, 404)
        self.assertEqual(self.reader.get(replacement_path).status_code, 200)

    def image_age(self, image_id):
        with self.session() as db:
            row = db.get(ArticleImageLifecycle, UUID(image_id))
            self.assertIsNotNone(row)
            return row.unreferenced_since.replace(tzinfo=timezone.utc) if row.unreferenced_since else None

    def sweep(self, now):
        with self.session() as db:
            article_image_cleanup.collect_unused(db, now=now)

    def test_last_reference_and_reuse_restart_grace_for_old_shared_images(self):
        unused, shared, draft_only = (self.upload() for _ in range(3))

        def path(image_id):
            return article_images.image_path(UUID(image_id))

        since = self.image_age(unused)
        old_timestamp = (since - timedelta(days=180)).timestamp()
        os.utime(path(shared), (old_timestamp, old_timestamp))
        first = self.create(draft(image=shared), publish=True)
        second = self.create(draft(image=shared))
        first = self.save(first, draft(image=draft_only))
        self.assertIsNone(self.image_age(shared))
        self.assertIsNone(self.image_age(draft_only))

        future = since + timedelta(days=8)
        self.sweep(since + timedelta(days=6))
        self.assertTrue(path(unused).exists())
        self.sweep(future)
        self.assertFalse(path(unused).exists())
        self.assertTrue(path(shared).exists())
        self.assertTrue(path(draft_only).exists())
        first = self.save(first, draft(image=draft_only), publish=True)
        self.assertIsNone(self.image_age(shared))  # Still in the second article's draft.
        self.sweep(future)
        self.assertTrue(path(shared).exists())

        second = self.save(second, draft())
        detached = self.image_age(shared)
        self.assertGreater(detached, since)
        self.sweep(detached + timedelta(days=7, seconds=-1))
        self.assertTrue(path(shared).exists())
        second = self.save(second, draft(image=shared))
        self.assertIsNone(self.image_age(shared))
        self.sweep(detached + timedelta(days=8))
        self.assertTrue(path(shared).exists())
        self.save(second, draft())
        detached_again = self.image_age(shared)
        self.assertGreater(detached_again, detached)
        self.sweep(detached_again + timedelta(days=7))
        self.assertFalse(path(shared).exists())
        self.assertTrue(path(draft_only).exists())
        self.assertEqual(self.admin.post(ADMIN_URL, json={"draft": draft(image=shared), "publish": True}).status_code, 422)

    def test_old_untracked_files_and_retry_without_an_article_operation(self):
        legacy = self.root / f"{uuid4()}.webp"
        legacy.write_bytes(b"unused legacy file")
        unrelated = self.root / "other.webp"
        unrelated.write_bytes(b"unmanaged file")
        outside = self.root / "checks"
        outside.mkdir()
        other = outside / f"{uuid4()}.webp"
        other.write_bytes(b"unmanaged subdirectory")
        old = (datetime.now(timezone.utc) - timedelta(days=180)).timestamp()
        os.utime(legacy, (old, old))
        now = datetime.now(timezone.utc)
        self.sweep(now)
        self.assertEqual(self.image_age(legacy.stem), now)
        self.assertTrue(legacy.exists())

        with patch("main.SessionLocal", self.session), patch("main.cleanup_stale_uploads", autospec=True), \
                patch("main.os.environ", {"UPLOAD_CLEANUP_INTERVAL_MINUTES": "5"}), \
                patch.object(article_image_cleanup, "GRACE_PERIOD", timedelta(0)), \
                patch("main.asyncio.sleep", side_effect=[None, None, asyncio.CancelledError]) as sleep:
            original_unlink = Path.unlink

            def unlink(path, **kwargs):
                if path == legacy and not failures:
                    failures.append(path)
                    raise PermissionError("temporary filesystem failure")
                original_unlink(path, **kwargs)

            failures = []
            with patch.object(Path, "unlink", unlink), self.assertLogs(article_image_cleanup.logger, level="WARNING"):
                with self.assertRaises(asyncio.CancelledError):
                    asyncio.run(periodic_upload_cleanup())
        self.assertEqual(failures, [legacy])
        self.assertEqual(sleep.await_count, 3)
        self.assertFalse(legacy.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(other.exists())

    def test_championship_order_and_standalone_guides(self):
        earlier = self.create(draft("Earlier"), publish=True)
        latest = self.create(draft("Latest"), publish=True)
        other = self.create(draft("Season 2", championship=2), publish=True)
        guide = self.create(draft("Sakura", kind="guide", championship=None, characters=[90, 90]), publish=True)
        guide_without_character = self.create(draft("Guide", kind="guide", championship=None), publish=True)

        season_url = f"{ARTICLE_URL}/season/1"
        season = self.reader.get(season_url).json()
        self.assertEqual(season["latest"]["id"], latest["id"])
        self.assertIn("body", season["latest"])
        self.assertEqual([item["id"] for item in season["earlier"]], [earlier["id"]])
        self.assertNotIn("body", season["earlier"][0])
        self.assertEqual(self.reader.get(f"{ARTICLE_URL}/season/2").json()["latest"]["id"], other["id"])
        guides = self.reader.get(f"{ARTICLE_URL}/guides").json()
        self.assertEqual([item["id"] for item in guides], [guide_without_character["id"], guide["id"]])
        self.assertEqual(self.reader.get(f"{ARTICLE_URL}/{guide['id']}").json()["character_ids"], [90])

        moved = self.save(latest, draft("Guide draft", kind="guide", championship=None))
        self.assertEqual(self.reader.get(season_url).json()["latest"]["id"], latest["id"])
        self.assertNotIn(moved["id"], [item["id"] for item in self.reader.get(f"{ARTICLE_URL}/guides").json()])
        self.save(moved, moved["draft"], publish=True)
        self.assertEqual(self.reader.get(season_url).json()["latest"]["id"], earlier["id"])

    def test_management_checks_permissions_on_all_operations(self):
        article = self.create(draft())
        path = f"{ADMIN_URL}/{article['id']}"
        for client, status in ((self.reader, 401), (self.provider, 403)):
            with self.subTest(status=status):
                self.assertEqual(client.get(ADMIN_URL).status_code, status)
                self.assertEqual(client.get(path).status_code, status)
                self.assertEqual(client.post(ADMIN_URL, json={"draft": draft()}).status_code, status)
                self.assertEqual(client.put(path, json={
                    "draft": draft(), "publish": True, "revision": article["revision"],
                }).status_code, status)
                self.assertEqual(client.post(f"{ADMIN_URL}/images", files={
                    "file": ("screenshot.png", b"abc", "image/png"),
                }).status_code, status)

    def test_rejects_invalid_links_invalid_images_and_incomplete_publications(self):
        for link in ("javascript:alert(1)", "//example.test/link", "/\\example.test/link", "https://user@example.test/"):
            with self.subTest(link=link):
                body = draft()
                body["body"]["content"][0]["content"][0]["marks"][0]["attrs"]["href"] = link
                self.assertEqual(self.admin.post(ADMIN_URL, json={"draft": body}).status_code, 422)
        self.assertEqual(self.admin.post(f"{ADMIN_URL}/images", files={
            "file": ("screenshot.png", b"abc", "image/png"),
        }).status_code, 422)
        self.assertEqual(self.admin.post(ADMIN_URL, json={"draft": draft(championship=None), "publish": True}).status_code, 422)
        self.assertEqual(self.admin.post(ADMIN_URL, json={
            "draft": draft(kind="guide", championship=None, characters=[901]), "publish": True,
        }).status_code, 422)
