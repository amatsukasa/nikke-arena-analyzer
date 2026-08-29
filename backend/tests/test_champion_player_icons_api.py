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

    def test_upload_accepts_jpeg_png_webp_and_normalizes_to_player_id_png(self):
        formats = ((".jpg", "image/jpeg"), (".png", "image/png"), (".webp", "image/webp"))
        expected_url = f"/api/uploads/player_icons/tournament_{self.champion.id}/player_{self.player.id}.png"
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
        self.assertEqual(path.read_bytes(), replacement_bytes)
        self.db.refresh(self.player)
        self.assertEqual(self.player.icon_url, first["icon_url"])
        self.assertEqual(list(path.parent.glob(".*")), [])

    def test_png_encoding_failure_preserves_old_image_and_cleans_temporaries(self):
        self._put(self._image_bytes(".png", 30))
        path, old_url = main.champion_player_icon_location(self.champion.id, self.player.id)
        old_bytes = path.read_bytes()
        with patch.object(main, "write_lossless_png", return_value=False):
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
            if source_path.name.startswith(f".{path.name}.") and source_path.suffix == ".png" and Path(destination) == path:
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
        oversized_shapes = (
            (1, main.CHAMPION_ICON_MAX_WIDTH + 1, 3),
            (main.CHAMPION_ICON_MAX_HEIGHT + 1, 1, 3),
            (5_001, 5_001, 3),
        )
        for shape in oversized_shapes:
            decoded = np.lib.stride_tricks.as_strided(
                np.zeros(1, dtype=np.uint8), shape=shape, strides=(0, 0, 0)
            )
            with patch("cv2.imread", return_value=decoded):
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
            (main.PLAYER_ICONS_DIR / f"tournament_{self.full.id}" / "seed_1.png").is_file()
        )


if __name__ == "__main__":
    unittest.main()
