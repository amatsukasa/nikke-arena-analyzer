"""Phase 4B tests for champion result-image analysis without persistence."""

import asyncio
from datetime import date
from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import mock_open, patch

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
from services.champion_result import normalize_champion_result  # noqa: E402


class FakeForm:
    def __init__(self, images, extras=None):
        self.images = images
        self.extras = extras or {}

    def getlist(self, key):
        return self.images if key == "image" else []

    def multi_items(self):
        return [("image", image) for image in self.images] + list(self.extras.items())


class FakeRequest:
    def __init__(self, images, extras=None):
        self.form_data = FakeForm(images, extras)
        self.form_called = False

    async def form(self, **kwargs):
        self.form_called = True
        self.form_kwargs = kwargs
        return self.form_data


class ChampionResultAnalysisApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original_upload_directory = main.UPLOAD_DIR
        main.UPLOAD_DIR = self.temp_directory.name
        self.delete_patcher = patch.object(
            main, "delete_upload_file",
            side_effect=lambda path: Path(path).unlink(missing_ok=True),
        )
        self.delete_patcher.start()
        self.owner = self._user("result-owner@example.invalid", "contributor")
        self.admin = self._user("result-admin@example.invalid", "admin")
        self.other = self._user("result-other@example.invalid", "contributor")
        self.tournament = self._tournament("champion", "champion_8", self.owner)
        self.full = self._tournament("full", "full_64", self.owner)
        self.players = [self._player(slot, None if slot == 2 else slot) for slot in range(1, 9)]
        for player in self.players:
            self._complete_deck(player)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.delete_patcher.stop()
        main.UPLOAD_DIR = self.original_upload_directory
        self.temp_directory.cleanup()

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

    def _player(self, slot, seed):
        player = models.Player(
            tournament_id=self.tournament.id, champion_slot=slot,
            seed_number=seed, name=f"Player {seed}" if seed else f"champion_slot_{slot}",
        )
        self.db.add(player); self.db.flush()
        return player

    def _complete_deck(self, player):
        deck_set = models.DeckSet(player_id=player.id)
        self.db.add(deck_set); self.db.flush()
        for team_number in range(1, 6):
            first = (team_number - 1) * 5 + 1
            self.db.add(models.DeckTeam(
                deck_set_id=deck_set.id, team_number=team_number,
                char1_id=first, char2_id=first + 1, char3_id=first + 2,
                char4_id=first + 3, char5_id=first + 4,
            ))

    @staticmethod
    def _image_bytes(extension=".png"):
        image = np.full((32, 48, 3), 100, dtype=np.uint8)
        success, encoded = cv2.imencode(extension, image)
        if not success:
            raise RuntimeError("test image encoding failed")
        return encoded.tobytes()

    @staticmethod
    def _upload(data, content_type="image/png"):
        return UploadFile(BytesIO(data), filename="ignored-client-name.dat", headers={"content-type": content_type})

    @staticmethod
    def _raw(sides):
        winner = "left" if sides.count("left") >= 3 else "right"
        return {
            "rounds": [
                {"round": number, "left": "WIN" if side == "left" else "LOSE", "right": "LOSE" if side == "left" else "WIN"}
                for number, side in enumerate(sides, start=1)
            ],
            "winner": winner,
        }

    def _analyze(self, raw=None, request=None, stage="quarterfinal", slot=1, user=None):
        request = request or FakeRequest([self._upload(self._image_bytes())])
        with patch.object(main, "extract_match_results", return_value=raw or self._raw(["left"] * 5)):
            return asyncio.run(main.analyze_champion_match_result(
                self.tournament.id, stage, slot, request, self.db, user or self.owner
            ))

    def _save_qf(self, slot, attacker_index, defender_index):
        attacker = self.players[attacker_index]
        defender = self.players[defender_index]
        payload = schemas.ChampionMatchUpsert(
            winner_id=attacker.id,
            round_results=[{"round_number": number, "winner_id": attacker.id if number <= 3 else defender.id} for number in range(1, 6)],
        )
        main.save_champion_match(self.tournament.id, "quarterfinal", slot, payload, self.db, self.owner)

    def _assert_async_status(self, status, tournament, stage, slot, request, user):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.analyze_champion_match_result(tournament, stage, slot, request, self.db, user))
        self.assertEqual(raised.exception.status_code, status)

    def test_qf_ready_maps_left_right_to_fixed_players_in_round_order(self):
        raw = self._raw(["left", "right", "left", "right", "left"])
        response = schemas.ChampionMatchAnalysisResponse.model_validate(self._analyze(raw))
        self.assertEqual(response.attacker.id, self.players[0].id)
        self.assertEqual(response.defender.id, self.players[1].id)
        self.assertIsNone(response.defender.seed_number)
        self.assertEqual([item.round_number for item in response.round_results], [1, 2, 3, 4, 5])
        self.assertEqual([item.winner_id for item in response.round_results], [self.players[0].id, self.players[1].id, self.players[0].id, self.players[1].id, self.players[0].id])
        self.assertEqual(response.winner_id, self.players[0].id)
        self.assertTrue(response.complete)
        self.assertEqual(response.issues, [])

    def test_left_five_right_five_and_two_three_majorities(self):
        cases = (
            (["left"] * 5, self.players[0].id),
            (["right"] * 5, self.players[1].id),
            (["left", "left", "right", "right", "right"], self.players[1].id),
        )
        for sides, winner_id in cases:
            response = self._analyze(self._raw(sides))
            self.assertEqual(response["winner_id"], winner_id)
            self.assertTrue(response["complete"])

    def test_unresolved_missing_extra_duplicate_and_invalid_results_are_safe(self):
        variants = []
        one_unresolved = self._raw(["left"] * 5); one_unresolved["rounds"][2] = {"round": 3, "left": None, "right": None}; variants.append(one_unresolved)
        multiple = self._raw(["left"] * 5); multiple["rounds"][1]["left"] = None; multiple["rounds"][3]["right"] = "WIN"; variants.append(multiple)
        variants.append({"rounds": self._raw(["left"] * 5)["rounds"][:4]})
        variants.append({"rounds": self._raw(["left"] * 5)["rounds"] + [{"round": 6, "left": "WIN", "right": "LOSE"}]})
        duplicate = self._raw(["left"] * 5); duplicate["rounds"][4]["round"] = 4; variants.append(duplicate)
        invalid = self._raw(["left"] * 5); invalid["rounds"][0] = {"round": 1, "left": "UNKNOWN", "right": "LOSE"}; variants.append(invalid)
        for raw in variants:
            converted = normalize_champion_result(raw, self.players[0].id, self.players[1].id)
            self.assertFalse(converted["complete"])
            self.assertIsNone(converted["winner_id"])
            self.assertTrue(converted["issues"])
            self.assertEqual([item["round_number"] for item in converted["round_results"]], [1, 2, 3, 4, 5])

        reversed_suspicion = self._raw(["left"] * 5)
        reversed_suspicion["winner"] = "right"
        converted = normalize_champion_result(
            reversed_suspicion, self.players[0].id, self.players[1].id
        )
        self.assertFalse(converted["complete"])
        self.assertIsNone(converted["winner_id"])
        self.assertTrue(any("矛盾" in issue for issue in converted["issues"]))

    def test_sf_and_final_require_complete_upstream_before_form_or_analysis(self):
        for stage in ("semifinal", "final"):
            request = FakeRequest([self._upload(self._image_bytes())])
            with patch.object(main, "extract_match_results") as analyzer:
                self._assert_async_status(409, self.tournament.id, stage, 1, request, self.owner)
            self.assertFalse(request.form_called)
            analyzer.assert_not_called()
        self._save_qf(1, 0, 1); self._save_qf(2, 2, 3)
        response = schemas.ChampionMatchAnalysisResponse.model_validate(
            self._analyze(stage="semifinal", slot=1)
        )
        self.assertEqual((response.attacker.id, response.defender.id), (self.players[0].id, self.players[2].id))

    def test_incomplete_deck_scope_permissions_not_found_and_invalid_slot_precede_image(self):
        self.db.delete(self.players[0].deck_sets[0]); self.db.commit()
        cases = (
            (409, self.tournament.id, "quarterfinal", 1, self.owner),
            (409, self.full.id, "quarterfinal", 1, self.owner),
            (403, self.tournament.id, "quarterfinal", 1, self.other),
            (401, self.tournament.id, "quarterfinal", 1, None),
            (404, 999999, "quarterfinal", 1, self.owner),
            (422, self.tournament.id, "group", 1, self.owner),
            (422, self.tournament.id, "quarterfinal", 5, self.owner),
        )
        for status, tournament_id, stage, slot, user in cases:
            request = FakeRequest([self._upload(self._image_bytes())])
            with patch.object(main, "extract_match_results") as analyzer:
                self._assert_async_status(status, tournament_id, stage, slot, request, user)
            self.assertFalse(request.form_called)
            analyzer.assert_not_called()

    def test_jpeg_png_webp_validation_and_no_database_writes(self):
        before = (self.db.query(models.Match).count(), self.db.query(models.RoundResult).count())
        for extension, mime in ((".jpg", "image/jpeg"), (".png", "image/png"), (".webp", "image/webp")):
            request = FakeRequest([self._upload(self._image_bytes(extension), mime)])
            response = self._analyze(request=request)
            self.assertTrue(response["complete"])
            self.assertNotIn(str(Path(self.temp_directory.name).resolve()), str(response))
            self.assertEqual(list(Path(self.temp_directory.name).iterdir()), [])
        self.assertEqual((self.db.query(models.Match).count(), self.db.query(models.RoundResult).count()), before)

    def test_image_count_extra_fields_empty_size_mime_and_decode_validation(self):
        cases = (
            (FakeRequest([]), 422),
            (FakeRequest([self._upload(self._image_bytes()), self._upload(self._image_bytes())]), 422),
            (FakeRequest([self._upload(self._image_bytes())], {"attacker_id": "1"}), 422),
            (FakeRequest([self._upload(b"")]), 422),
            (FakeRequest([self._upload(b"x" * (main.CHAMPION_RESULT_MAX_BYTES + 1))]), 413),
            (FakeRequest([self._upload(self._image_bytes(), "text/plain")]), 422),
            (FakeRequest([self._upload(b"not-image", "image/png")]), 422),
        )
        for request, status in cases:
            self._assert_async_status(status, self.tournament.id, "quarterfinal", 1, request, self.owner)
            self.assertEqual(list(Path(self.temp_directory.name).iterdir()), [])

    def test_extra_fields_and_duplicate_images_stop_before_decode_ocr_db_or_cache(self):
        requests = (
            FakeRequest([self._upload(self._image_bytes())], {"winner_id": "1"}),
            FakeRequest([self._upload(self._image_bytes())], {"attacker_id": "1", "seed": "2"}),
            FakeRequest([self._upload(self._image_bytes()), self._upload(self._image_bytes())]),
        )
        for request in requests:
            with (
                patch("cv2.imread") as decode,
                patch.object(main, "extract_match_results") as ocr,
                patch.object(self.db, "commit", wraps=self.db.commit) as commit,
                patch.object(main, "invalidate_dashboard_cache") as invalidate,
            ):
                self._assert_async_status(
                    422,
                    self.tournament.id,
                    "quarterfinal",
                    1,
                    request,
                    self.owner,
                )
            decode.assert_not_called()
            ocr.assert_not_called()
            commit.assert_not_called()
            invalidate.assert_not_called()
            self.assertEqual(self.db.query(models.Match).count(), 0)
            self.assertEqual(self.db.query(models.RoundResult).count(), 0)

    def test_analysis_exception_removes_temporary_file_and_returns_no_partial_data(self):
        request = FakeRequest([self._upload(self._image_bytes())])
        observed = []
        def fail(path):
            observed.append(path)
            self.assertTrue(Path(path).is_file())
            raise RuntimeError("model failed")
        with patch.object(main, "extract_match_results", side_effect=fail):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.analyze_champion_match_result(
                    self.tournament.id, "quarterfinal", 1, request, self.db, self.owner
                ))
        self.assertEqual(raised.exception.status_code, 500)
        self.assertTrue(all(not Path(path).exists() for path in observed))
        self.assertEqual(list(Path(self.temp_directory.name).iterdir()), [])

    def test_route_registration_and_legacy_result_api_remain_separate(self):
        expected = {
            ("POST", "/api/tournaments/{tournament_id}/matches/{bracket_stage}/{bracket_slot}/analyze", main.analyze_champion_match_result),
            ("POST", "/api/analyze/match_result", main.analyze_match_result),
        }
        routes = {(method, route.path, route.endpoint) for route in main.app.routes for method in (getattr(route, "methods", None) or set())}
        self.assertTrue(expected <= routes)
        legacy_raw = self._raw(["left", "right", "left", "right", "left"])
        with (
            patch("builtins.open", mock_open()),
            patch.object(main.shutil, "copyfileobj"),
            patch("services.match_processor.extract_match_results", return_value=legacy_raw),
        ):
            legacy = asyncio.run(main.analyze_match_result(
                self.tournament.id,
                1,
                2,
                "Groups",
                self._upload(self._image_bytes()),
            ))
        self.assertEqual(legacy, {
            "tournament_id": self.tournament.id,
            "attacker_seed": 1,
            "defender_seed": 2,
            "stage": "Groups",
            "rounds": legacy_raw["rounds"],
            "winner": legacy_raw["winner"],
        })


if __name__ == "__main__":
    unittest.main()
