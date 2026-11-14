"""Phase 3C tests for player-id based champion icon management."""

import asyncio
from datetime import date
from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DASHBOARD_CACHE_TTL_SECONDS", "60")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException, UploadFile  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402


class ChampionPlayerIconApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        main._dashboard_cache.clear()
        self.icon_directory = tempfile.TemporaryDirectory()
        self.original_icon_directory = main.PLAYER_ICONS_DIR
        main.PLAYER_ICONS_DIR = Path(self.icon_directory.name).resolve()
        self.db = SessionLocal()
        self.owner = self._user("icon-owner@example.invalid", "contributor")
        self.admin = self._user("icon-admin@example.invalid", "admin")
        self.other = self._user("icon-other@example.invalid", "contributor")
        self.champion = self._tournament("champion", "champion_8", self.owner)
        self.other_champion = self._tournament("other", "champion_8", self.other)
        self.full = self._tournament("full", "full_64", self.owner)
        self.player = self._player(self.champion, 1, None)
        self.second_player = self._player(self.champion, 2, 20)
        self.other_player = self._player(self.other_champion, 1, 10)
        self.full_player = self._player(self.full, None, 1)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        main.PLAYER_ICONS_DIR = self.original_icon_directory
        self.icon_directory.cleanup()
        main._dashboard_cache.clear()

    def _user(self, email, role):
        user = models.AppUser(email=email, hashed_password="unused", role=role, approval_status="approved")
        self.db.add(user); self.db.flush()
        return user

    def _tournament(self, name, scope, owner):
        tournament = models.Tournament(
            name=name, date=date(2026, 1, 1), registration_scope=scope,
            created_by=owner.id, publication_status="draft",
        )
        self.db.add(tournament); self.db.flush()
        return tournament

    def _player(self, tournament, slot, seed):
        player = models.Player(
            tournament_id=tournament.id, champion_slot=slot, seed_number=seed,
            name=f"champion_slot_{slot}" if seed is None else f"Player {seed}",
        )
        self.db.add(player); self.db.flush()
        return player

    @staticmethod
    def _image_bytes(extension, value=80):
        image = np.full((24, 32, 3), value, dtype=np.uint8)
        success, encoded = cv2.imencode(extension, image)
        if not success:
            raise RuntimeError(f"Unable to encode test image as {extension}")
        return encoded.tobytes()

    @staticmethod
    def _upload(data, content_type, filename="client-name-do-not-use.bin"):
        return UploadFile(BytesIO(data), filename=filename, headers={"content-type": content_type})

    def _put(self, data=None, content_type="image/png", player=None, tournament=None, user=None):
        return asyncio.run(main.upload_champion_player_icon(
            (tournament or self.champion).id,
            (player or self.player).id,
            self._upload(data if data is not None else self._image_bytes(".png"), content_type),
            self.db, user or self.owner,
        ))

    def _assert_status(self, status, function, *args):
        with self.assertRaises(HTTPException) as raised:
            function(*args)
        self.assertEqual(raised.exception.status_code, status)

    def test_upload_accepts_jpeg_png_webp_and_normalizes_to_player_id_webp(self):
        formats = ((".jpg", "image/jpeg"), (".png", "image/png"), (".webp", "image/webp"))
        expected_url = f"/api/uploads/player_icons/tournament_{self.champion.id}/player_{self.player.id}.webp"
        for extension, content_type in formats:
            response = schemas.ChampionPlayerIconResponse.model_validate(
                self._put(self._image_bytes(extension), content_type)
            )
            path, _ = main.champion_player_icon_location(self.champion.id, self.player.id)
            self.assertEqual(response.icon_url, expected_url)
            self.assertTrue(path.is_file())
            self.assertIsNotNone(cv2.imread(str(path)))
            self.assertNotIn("client-name", str(path))

    def test_empty_oversized_mime_spoof_and_non_image_are_rejected_without_file(self):
        cases = (
            (b"", "image/png", 422),
            (b"x" * (main.CHAMPION_ICON_MAX_BYTES + 1), "image/png", 413),
            (self._image_bytes(".png"), "text/plain", 422),
            (b"not an image", "image/png", 422),
        )
        for data, content_type, status in cases:
            with self.assertRaises(HTTPException) as raised:
                self._put(data, content_type)
            self.assertEqual(raised.exception.status_code, status)
            path, _ = main.champion_player_icon_location(self.champion.id, self.player.id)
            self.assertFalse(path.exists())
            self.assertIsNone(self.db.get(models.Player, self.player.id).icon_url)

    def test_reupload_atomically_replaces_and_database_failure_restores_old_image(self):
        first = self._put(self._image_bytes(".png", 30))
        path, _ = main.champion_player_icon_location(self.champion.id, self.player.id)
        original_bytes = path.read_bytes()
        second = self._put(self._image_bytes(".png", 180))
        self.assertEqual(second["icon_url"], first["icon_url"])
        replacement_bytes = path.read_bytes()
        self.assertNotEqual(replacement_bytes, original_bytes)

        with patch.object(self.db, "commit", side_effect=RuntimeError("database failed")):
            with self.assertRaises(RuntimeError):
                self._put(self._image_bytes(".png", 240))
        self.assertNotEqual(path.read_bytes(), replacement_bytes)
        self.db.refresh(self.player)
        self.assertEqual(self.player.icon_url, first["icon_url"])
        self.assertTrue(list(path.parent.glob("*.backup")) or list(path.parent.glob(".*.backup")))

    def test_png_encoding_failure_preserves_old_image_and_cleans_temporaries(self):
        self._put(self._image_bytes(".png", 30))
        path, old_url = main.champion_player_icon_location(self.champion.id, self.player.id)
        old_bytes = path.read_bytes()
        with patch.object(main, "write_webp", side_effect=main.InvalidIcon("encoding failed")):
            with self.assertRaises(HTTPException) as raised:
                self._put(self._image_bytes(".png", 180))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(path.read_bytes(), old_bytes)
        self.db.refresh(self.player)
        self.assertEqual(self.player.icon_url, old_url)
        self.assertEqual(list(path.parent.glob(".*")), [])

    def test_backup_move_failure_preserves_old_image(self):
        self._put(self._image_bytes(".png", 30))
        path, _ = main.champion_player_icon_location(self.champion.id, self.player.id)
        old_bytes = path.read_bytes()
        real_replace = os.replace

        def fail_backup(source, destination):
            if Path(source) == path and str(destination).endswith(".backup"):
                raise OSError("backup move failed")
            return real_replace(source, destination)

        with patch.object(main.os, "replace", side_effect=fail_backup):
            with self.assertRaises(OSError):
                self._put(self._image_bytes(".png", 180))
        self.assertEqual(path.read_bytes(), old_bytes)
        self.assertEqual(list(path.parent.glob(".*")), [])

    def test_new_image_replace_failure_after_backup_restores_old_image(self):
        self._put(self._image_bytes(".png", 30))
        path, _ = main.champion_player_icon_location(self.champion.id, self.player.id)
        old_bytes = path.read_bytes()
        real_replace = os.replace

        def fail_new_image(source, destination):
            source_path = Path(source)
            if source_path.name.startswith(f".{path.name}.") and source_path.suffix == ".webp" and Path(destination) == path:
                raise OSError("new image placement failed")
            return real_replace(source, destination)

        with patch.object(main.os, "replace", side_effect=fail_new_image):
            with self.assertRaises(OSError):
                self._put(self._image_bytes(".png", 180))
        self.assertEqual(path.read_bytes(), old_bytes)
        self.assertEqual(list(path.parent.glob(".*")), [])

    def test_database_flush_failure_restores_old_image(self):
        self._put(self._image_bytes(".png", 30))
        path, old_url = main.champion_player_icon_location(self.champion.id, self.player.id)
        old_bytes = path.read_bytes()
        with patch.object(self.db, "flush", side_effect=RuntimeError("flush failed")):
            with self.assertRaises(RuntimeError):
                self._put(self._image_bytes(".png", 180))
        self.assertEqual(path.read_bytes(), old_bytes)
        self.db.refresh(self.player)
        self.assertEqual(self.player.icon_url, old_url)
        self.assertEqual(list(path.parent.glob(".*")), [])

    def test_backup_cleanup_failure_keeps_new_image_and_database_value(self):
        self._put(self._image_bytes(".png", 30))
        path, icon_url = main.champion_player_icon_location(self.champion.id, self.player.id)
        old_bytes = path.read_bytes()
        real_unlink = Path.unlink

        def fail_backup_unlink(target, *args, **kwargs):
            if str(target).endswith(".backup"):
                raise OSError("backup cleanup failed")
            return real_unlink(target, *args, **kwargs)

        with patch.object(Path, "unlink", autospec=True, side_effect=fail_backup_unlink), patch("builtins.print") as log:
            response = self._put(self._image_bytes(".png", 180))
        self.assertEqual(response["icon_url"], icon_url)
        self.assertNotEqual(path.read_bytes(), old_bytes)
        self.db.refresh(self.player)
        self.assertEqual(self.player.icon_url, icon_url)
        self.assertTrue(any(str(item).endswith(".backup") for item in path.parent.glob(".*")))
        self.assertIn("backup cleanup failed", log.call_args.args[0])

    def test_temporary_names_are_unique_and_normal_success_leaves_no_hidden_files(self):
        with patch.object(main, "champion_icon_temporary_paths", wraps=main.champion_icon_temporary_paths) as paths:
            self._put(self._image_bytes(".png", 30))
            self._put(self._image_bytes(".png", 180))
        first_token = paths.call_args_list[0].args[1]
        second_token = paths.call_args_list[1].args[1]
        self.assertNotEqual(first_token, second_token)
        first_paths = main.champion_icon_temporary_paths(paths.call_args_list[0].args[0], first_token)
        second_paths = main.champion_icon_temporary_paths(paths.call_args_list[1].args[0], second_token)
        self.assertTrue(set(first_paths).isdisjoint(second_paths))
        final_path, _ = main.champion_player_icon_location(self.champion.id, self.player.id)
        self.assertEqual(list(final_path.parent.glob(".*")), [])

    def test_decoded_dimension_limits_reject_width_height_and_total_pixels(self):
        with patch("services.player_icons.MAX_DIMENSION", 20):
            with self.assertRaises(HTTPException) as raised:
                self._put(self._image_bytes(".png"))
        self.assertEqual(raised.exception.status_code, 413)
        with patch("services.player_icons.MAX_PIXELS", 100):
            with self.assertRaises(HTTPException) as raised:
                self._put(self._image_bytes(".png"))
        self.assertEqual(raised.exception.status_code, 413)
        self._put(self._image_bytes(".png"))

    def test_seed_and_name_changes_do_not_change_url_or_path(self):
        response = self._put()
        original_path, original_url = main.champion_player_icon_location(self.champion.id, self.player.id)
        self.player.seed_number = 64
        self.player.name = "Player 64"
        self.db.commit()
        replaced = self._put(self._image_bytes(".jpg"), "image/jpeg")
        current_path, current_url = main.champion_player_icon_location(self.champion.id, self.player.id)
        self.assertEqual((current_path, current_url), (original_path, original_url))
        self.assertEqual(replaced["icon_url"], response["icon_url"])

    def test_delete_is_idempotent_and_does_not_touch_another_player(self):
        self._put(player=self.player)
        self._put(player=self.second_player)
        first_path, _ = main.champion_player_icon_location(self.champion.id, self.player.id)
        second_path, second_url = main.champion_player_icon_location(self.champion.id, self.second_player.id)
        deleted = main.delete_champion_player_icon(self.champion.id, self.player.id, self.db, self.owner)
        self.assertIsNone(deleted["icon_url"])
        self.assertFalse(first_path.exists())
        self.assertTrue(second_path.exists())
        self.assertEqual(self.db.get(models.Player, self.second_player.id).icon_url, second_url)
        repeated = main.delete_champion_player_icon(self.champion.id, self.player.id, self.db, self.owner)
        self.assertIsNone(repeated["icon_url"])

    def test_upload_and_delete_scope_membership_permissions(self):
        upload = lambda tournament, player, user: asyncio.run(main.upload_champion_player_icon(
            tournament.id, player.id, self._upload(self._image_bytes(".png"), "image/png"), self.db, user
        ))
        self._assert_status(409, upload, self.full, self.full_player, self.owner)
        self._assert_status(404, upload, self.champion, self.other_player, self.owner)
        self._assert_status(403, upload, self.champion, self.player, self.other)
        self._assert_status(401, upload, self.champion, self.player, None)
        self._put(user=self.admin)
        self._assert_status(409, main.delete_champion_player_icon, self.full.id, self.full_player.id, self.db, self.owner)
        self._assert_status(404, main.delete_champion_player_icon, self.champion.id, self.other_player.id, self.db, self.owner)
        self._assert_status(403, main.delete_champion_player_icon, self.champion.id, self.player.id, self.db, self.other)
        self._assert_status(401, main.delete_champion_player_icon, self.champion.id, self.player.id, self.db, None)

    def test_player_detail_and_slots_include_icon_url(self):
        response = self._put()
        detail = schemas.ChampionPlayerResponse.model_validate(
            main.get_champion_player_by_id(self.champion.id, self.player.id, self.db, self.owner)
        )
        slots = schemas.ChampionSlotsResponse.model_validate(
            main.get_champion_slots(self.champion.id, self.db, self.owner)
        )
        self.assertEqual(detail.icon_url, response["icon_url"])
        self.assertEqual(slots.slots[0].player.icon_url, response["icon_url"])

    def test_cache_invalidation_and_failure_do_not_fail_file_operation(self):
        key = main._dashboard_cache_key(self.champion.id, "stats")
        main._dashboard_cache[key] = {"value": {}, "expires_at": float("inf")}
        self._put()
        self.assertNotIn(key, main._dashboard_cache)
        with patch.object(main, "invalidate_dashboard_cache", side_effect=RuntimeError("cache failed")), patch("builtins.print") as log:
            response = self._put(self._image_bytes(".png", 150))
        self.assertIsNotNone(response["icon_url"])
        self.assertIn(f"tournament={self.champion.id}", log.call_args.args[0])

    def test_routes_and_existing_seed_icon_api_contract_remain_registered(self):
        expected = {
            ("PUT", "/api/tournaments/{tournament_id}/players/by-id/{player_id}/icon", main.upload_champion_player_icon),
            ("DELETE", "/api/tournaments/{tournament_id}/players/by-id/{player_id}/icon", main.delete_champion_player_icon),
            ("POST", "/api/upload/player-icon", main.upload_player_icon),
        }
        routes = {(method, route.path, route.endpoint) for route in main.app.routes for method in (getattr(route, "methods", None) or set())}
        self.assertTrue(expected <= routes)

        legacy = asyncio.run(main.upload_player_icon(
            self._upload(self._image_bytes(".png"), "image/png"),
            self.full.id,
            self.full_player.seed_number,
            self.db,
            self.owner,
        ))
        self.assertEqual(legacy["player_id"], self.full_player.id)
        self.assertTrue(
            (main.PLAYER_ICONS_DIR / f"tournament_{self.full.id}" / "seed_1.webp").is_file()
        )

    def test_full64_rejects_corrupt_image_and_preserves_old_icon(self):
        good = asyncio.run(main.upload_player_icon(self._upload(self._image_bytes('.png'),'image/png'),self.full.id,1,self.db,self.owner))
        path=main.PLAYER_ICONS_DIR/f'tournament_{self.full.id}'/'seed_1.webp'
        previous=path.read_bytes()
        with self.assertRaises(HTTPException):
            asyncio.run(main.upload_player_icon(self._upload(b'broken','image/png'),self.full.id,1,self.db,self.owner))
        self.assertEqual(path.read_bytes(),previous)
        self.assertEqual(self.db.get(models.Player,self.full_player.id).icon_url,good['url'])

    def test_webp_mime_png_redirect_and_private_access(self):
        self._put()
        relative=f'player_icons/tournament_{self.champion.id}/player_{self.player.id}.webp'
        old_root=main.UPLOAD_DIR
        main.UPLOAD_DIR=str(main.PLAYER_ICONS_DIR.parent)
        # The fixture root is an arbitrary temp dir, so create a dedicated upload tree.
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/relative;target.parent.mkdir(parents=True)
            path,_=main.champion_player_icon_location(self.champion.id,self.player.id)
            shutil.copyfile(path,target);main.UPLOAD_DIR=directory
            try:
                response=main.get_upload(relative,self.db,self.owner)
                self.assertEqual(response.media_type,'image/webp')
                redirected=main.get_upload(relative[:-5]+'.png',self.db,self.owner)
                self.assertEqual(redirected.status_code,307)
                self.assertEqual(redirected.headers['location'],'/api/uploads/'+relative)
                self._assert_status(404,main.get_upload,relative,self.db,self.other)
                self._assert_status(404,main.get_upload,relative[:-5]+'.png',self.db,None)
                self.champion.publication_status='published';self.db.commit()
                self.assertEqual(main.get_upload(relative,self.db,self.owner).status_code,200)
                self._assert_status(404,main.get_upload,relative,self.db,None)
            finally:main.UPLOAD_DIR=old_root

    def test_existing_png_display_delete_and_mixed_formats(self):
        path,_=main.champion_player_icon_location(self.champion.id,self.player.id)
        path.parent.mkdir(parents=True,exist_ok=True)
        png_path=path.with_suffix('.png');png_path.write_bytes(self._image_bytes('.png'))
        self.player.icon_url=f'/api/uploads/player_icons/tournament_{self.champion.id}/player_{self.player.id}.png'
        self.db.commit()
        self._put();self.assertTrue(png_path.exists());self.assertTrue(path.exists())
        main.delete_champion_player_icon(self.champion.id,self.player.id,self.db,self.owner)
        self.assertFalse(png_path.exists());self.assertFalse(path.exists())

    def test_wrong_tournament_reference_and_paused_writes(self):
        foreign=f'/api/uploads/player_icons/tournament_{self.other_champion.id}/seed_1.webp'
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.update_player_info(self.full.id,1,{'icon_url':foreign},self.db,self.owner))
        self.assertEqual(raised.exception.status_code,422)
        with patch.dict(os.environ,{'PLAYER_ICON_WRITES_PAUSED':'1'}):
            self._assert_status(503,self._put)
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.upload_player_icon(self._upload(self._image_bytes('.png'),'image/png'),self.full.id,1,self.db,self.owner))
            self.assertEqual(raised.exception.status_code,503)

    def test_actual_rgba_upload_preserves_alpha(self):
        from PIL import Image
        im=Image.new('RGBA',(32,24));im.putdata([(i%256,80,120,i%256) for i in range(32*24)])
        stream=BytesIO();im.save(stream,'PNG');self._put(stream.getvalue())
        path,_=main.champion_player_icon_location(self.champion.id,self.player.id)
        with Image.open(path) as saved:
            self.assertEqual(saved.format,'WEBP');self.assertEqual(saved.size,im.size)
            self.assertEqual(saved.convert('RGBA').getchannel('A').tobytes(),im.getchannel('A').tobytes())

    def test_tournament_deletion_removes_both_formats_only_for_target(self):
        self._put();self._put(player=self.other_player,tournament=self.other_champion,user=self.other)
        path,_=main.champion_player_icon_location(self.champion.id,self.player.id)
        other,_=main.champion_player_icon_location(self.other_champion.id,self.other_player.id)
        path.with_suffix('.png').write_bytes(self._image_bytes('.png'))
        from services import upload_cleanup
        with patch.object(upload_cleanup,'PLAYER_ICONS_DIR',main.PLAYER_ICONS_DIR):
            main.delete_tournament(self.champion.id,self.db,self.owner)
        self.assertFalse(path.parent.exists());self.assertTrue(other.exists())

    def test_http_multipart_upload_and_image_response(self):
        import httpx
        overrides=dict(main.app.dependency_overrides)
        main.app.dependency_overrides[main.get_db]=lambda:self.db
        main.app.dependency_overrides[main.auth_module.get_current_user]=lambda:self.owner
        main.app.dependency_overrides[main.auth_module.get_current_user_optional]=lambda:self.owner
        old_upload=main.UPLOAD_DIR
        with tempfile.TemporaryDirectory() as directory:
            old_icons=main.PLAYER_ICONS_DIR
            main.UPLOAD_DIR=directory;main.PLAYER_ICONS_DIR=Path(directory)/'player_icons'
            async def requests():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url="http://test") as client:
                    response=await client.post('/api/upload/player-icon',data={'tournament_id':self.full.id,'seed_number':44},files={'image':('evil-name.png',self._image_bytes('.png'),'image/png')})
                    self.assertEqual(response.status_code,200,response.text)
                    url=response.json()['url'];self.assertTrue(url.endswith('.webp'))
                    served=await client.get(url);self.assertEqual(served.status_code,200)
                    self.assertEqual(served.headers['content-type'],'image/webp')
                    self.assertEqual(served.content[:4],b'RIFF')
                    response=await client.put(f'/api/tournaments/{self.champion.id}/players/by-id/{self.player.id}/icon',files={'image':('input.webp',self._image_bytes('.webp'),'image/webp')})
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual((await client.get(response.json()['icon_url'])).headers['content-type'],'image/webp')
            try:
                asyncio.run(requests())
            finally:
                main.UPLOAD_DIR=old_upload;main.PLAYER_ICONS_DIR=old_icons
                main.app.dependency_overrides.clear();main.app.dependency_overrides.update(overrides)

    def test_postgres_migration_commit_failure_retry_and_rollback(self):
        from scripts import migrate_player_icons as migration
        from sqlalchemy import event
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'uploads'/'player_icons'
            relative=f'tournament_{self.champion.id}/player_{self.player.id}.png'
            source=root/relative;source.parent.mkdir(parents=True);source.write_bytes(self._image_bytes('.png'))
            self.player.icon_url=migration.PREFIX+relative;self.db.commit()
            backup=base/'backup';migration.backup(engine,root,backup)
            manifest=migration.verify_backup(root,backup,True)
            def fail_update(conn,cursor,statement,parameters,context,executemany):
                if statement.startswith('UPDATE players SET icon_url='):raise RuntimeError('injected')
            event.listen(engine,'before_cursor_execute',fail_update)
            try:self.assertEqual(migration.run(engine,root,backup,True)['failed'],1)
            finally:event.remove(engine,'before_cursor_execute',fail_update)
            self.assertTrue(source.exists())
            self.assertEqual(migration.run(engine,root,backup,True)['success'],1)
            self.assertEqual(migration.run(engine,root,backup,True)['already_webp'],1)
            self.assertEqual(migration.rollback(engine,root,backup,manifest,True)[0]['status'],'restored')

    def test_lost_commit_ack_keeps_committed_webp_file(self):
        old_url=f'/api/uploads/player_icons/tournament_{self.champion.id}/player_{self.player.id}.png'
        self.player.icon_url=old_url;self.db.commit()
        real_commit=self.db.commit
        def lost_ack():
            real_commit()
            raise RuntimeError('lost acknowledgement')
        with patch.object(self.db,'commit',side_effect=lost_ack):
            with self.assertRaises(RuntimeError):self._put()
        path,new_url=main.champion_player_icon_location(self.champion.id,self.player.id)
        self.assertTrue(path.exists())
        self.db.refresh(self.player);self.assertEqual(self.player.icon_url,new_url)

    def test_same_url_lost_commit_ack_preserves_new_content(self):
        self._put(self._image_bytes('.png',30))
        path,url=main.champion_player_icon_location(self.champion.id,self.player.id)
        old=path.read_bytes();real=self.db.commit
        def lost():
            real();raise RuntimeError('lost acknowledgement')
        with patch.object(self.db,'commit',side_effect=lost):
            with self.assertRaises(RuntimeError):self._put(self._image_bytes('.png',180))
        self.assertNotEqual(path.read_bytes(),old)
        self.assertTrue(list(path.parent.glob('*.json')) or list(path.parent.glob('.*.recovery.json')))

    def test_interruption_after_backup_preserves_hash_recovery_record(self):
        import json,hashlib
        self._put();path,_=main.champion_player_icon_location(self.champion.id,self.player.id)
        original=path.read_bytes();replace=main.os.replace
        def interrupt(source,target):
            if str(target).endswith('.backup'):
                replace(source,target);raise SystemExit('simulated process interruption')
            replace(source,target)
        with patch.object(main.os,'replace',side_effect=interrupt):
            with self.assertRaises(SystemExit):self._put(self._image_bytes('.png',180))
        record=json.loads(next(path.parent.glob('.*.recovery.json')).read_text())
        self.assertEqual(record['old_sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual((path.parent/record['backup']).read_bytes(),original)

    def test_reference_compatibility_png_webp_none_and_legacy_cropped(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);icons=root/'player_icons';folder=icons/f'tournament_{self.full.id}';folder.mkdir(parents=True)
            png=folder/'seed_1.png';png.write_bytes(self._image_bytes('.png'))
            png_url=f'/api/uploads/player_icons/tournament_{self.full.id}/seed_1.png'
            with patch.object(main,'PLAYER_ICONS_DIR',icons):
                self.assertEqual(main.validated_player_icon_reference(png_url,self.full.id,self.db),png_url)
                self.assertIsNone(main.validated_player_icon_reference(None,self.full.id,self.db))
                self.full_player.icon_url=png_url;self.db.commit()
                response=asyncio.run(main.update_player_info(self.full.id,1,{},self.db,self.owner))
                self.assertEqual(response.icon_url,png_url)
                folder.joinpath('seed_1.webp').write_bytes(self._image_bytes('.webp'))
                self.full_player.icon_url=png_url[:-4]+'.webp';self.db.commit()
                self.assertEqual(main.validated_player_icon_reference(png_url,self.full.id,self.db),png_url[:-4]+'.webp')
            self.full_player.icon_url='/api/uploads/cropped/player_icon_legacy.png';self.db.commit()
            self.assertEqual(main.validated_player_icon_reference(self.full_player.icon_url,self.full.id,self.db),self.full_player.icon_url)
            with self.assertRaises(HTTPException):main.validated_player_icon_reference('https://untrusted.invalid/a.png',self.full.id,self.db)


if __name__ == "__main__":
    unittest.main()
