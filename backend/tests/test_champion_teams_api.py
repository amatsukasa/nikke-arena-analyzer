"""Phase 3B regression tests for champion deck analysis and persistence."""

import asyncio
from datetime import date
from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DASHBOARD_CACHE_TTL_SECONDS", "60")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException, UploadFile  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402


class FakeForm:
    def __init__(self, images, flags=None):
        self.values = {"images": images, "image_pre_cropped": flags or []}

    def getlist(self, key):
        return self.values.get(key, [])


class FakeRequest:
    def __init__(self, images, flags=None):
        self.form_data = FakeForm(images, flags)
        self.form_called = False

    async def form(self, **kwargs):
        self.form_called = True
        self.form_kwargs = kwargs
        return self.form_data


class ChampionTeamsApiTest(unittest.TestCase):
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
        self.upload_directory = tempfile.TemporaryDirectory()
        self.original_upload_directory = main.UPLOAD_DIR
        main.UPLOAD_DIR = self.upload_directory.name
        self.upload_delete_patcher = patch.object(
            main,
            "delete_upload_file",
            side_effect=lambda path: Path(path).unlink(missing_ok=True),
        )
        self.upload_delete_patcher.start()
        self.db = SessionLocal()
        self.owner = self._user("owner-3b@example.invalid", "contributor")
        self.admin = self._user("admin-3b@example.invalid", "admin")
        self.other = self._user("other-3b@example.invalid", "contributor")
        self.champion = self._tournament("champion", "champion_8", self.owner)
        self.other_champion = self._tournament("other", "champion_8", self.other)
        self.full = self._tournament("full", "full_64", self.owner)
        self.player = self._player(self.champion, 1, None)
        self.other_player = self._player(self.other_champion, 1, 17)
        self.full_player = self._player(self.full, None, 1)
        for character_id in range(1, 51):
            self.db.add(models.Character(id=character_id, name=f"Character {character_id}"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        main._dashboard_cache.clear()
        self.upload_delete_patcher.stop()
        main.UPLOAD_DIR = self.original_upload_directory
        self.upload_directory.cleanup()

    def _user(self, email, role):
        user = models.AppUser(email=email, hashed_password="unused", role=role, approval_status="approved")
        self.db.add(user)
        self.db.flush()
        return user

    def _tournament(self, name, scope, owner):
        tournament = models.Tournament(
            name=name, date=date(2026, 1, 1), registration_scope=scope,
            created_by=owner.id, publication_status="draft",
        )
        self.db.add(tournament)
        self.db.flush()
        return tournament

    def _player(self, tournament, slot, seed):
        player = models.Player(
            tournament_id=tournament.id, champion_slot=slot, seed_number=seed,
            name=f"champion_slot_{slot}" if seed is None else f"Player {seed}",
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _payload(self, offset=0, order=(1, 2, 3, 4, 5)):
        teams = []
        for team_number in order:
            first = offset + (team_number - 1) * 5 + 1
            teams.append({
                "team_number": team_number,
                "characters": [{"id": character_id, "collection_level": "none"} for character_id in range(first, first + 5)],
            })
        return schemas.ChampionTeamsUpsert(teams=teams)

    def _save(self, payload=None, player=None, tournament=None, user=None):
        return main.save_champion_teams(
            (tournament or self.champion).id,
            (player or self.player).id,
            payload or self._payload(), self.db, user or self.owner,
        )

    def _assert_status(self, status, function, *args):
        with self.assertRaises(HTTPException) as raised:
            function(*args)
        self.assertEqual(raised.exception.status_code, status)

    @staticmethod
    def _upload(content=b"image", content_type="image/png", name="deck.png"):
        return UploadFile(BytesIO(content), filename=name, headers={"content-type": content_type})

    def test_save_five_teams_orders_response_and_supports_null_seed(self):
        response = schemas.ChampionTeamsResponse.model_validate(
            self._save(self._payload(order=(5, 3, 1, 4, 2)))
        )
        self.assertEqual(response.status, "complete")
        self.assertEqual(response.player_id, self.player.id)
        self.assertEqual(response.champion_slot, 1)
        self.assertEqual([team.team_number for team in response.teams], [1, 2, 3, 4, 5])
        self.assertEqual(self.db.query(models.DeckSet).filter_by(player_id=self.player.id).count(), 1)
        self.assertEqual(self.db.query(models.DeckTeam).count(), 5)

    def test_payload_shape_and_team_number_validation(self):
        for count in (4, 6):
            data = self._payload().model_dump()
            data["teams"] = data["teams"][:count] if count == 4 else data["teams"] + [data["teams"][0]]
            self._assert_status(422, self._save, schemas.ChampionTeamsUpsert.model_validate(data))
        for numbers in ((1, 2, 3, 4, 4), (0, 2, 3, 4, 5), (1, 2, 3, 4, 6)):
            data = self._payload().model_dump()
            for team, number in zip(data["teams"], numbers):
                team["team_number"] = number
            self._assert_status(422, self._save, schemas.ChampionTeamsUpsert.model_validate(data))

    def test_character_count_unresolved_unknown_and_duplicates_rejected_before_change(self):
        variants = []
        for count in (4, 6):
            data = self._payload().model_dump()
            data["teams"][0]["characters"] = data["teams"][0]["characters"][:count]
            if count == 6:
                data["teams"][0]["characters"].append({"id": 26, "collection_level": None})
            variants.append(data)
        unresolved = self._payload().model_dump(); unresolved["teams"][0]["characters"][0]["id"] = 9999; variants.append(unresolved)
        unknown = self._payload().model_dump(); unknown["teams"][0]["characters"][0]["id"] = 999; variants.append(unknown)
        within = self._payload().model_dump(); within["teams"][0]["characters"][1]["id"] = 1; variants.append(within)
        across = self._payload().model_dump(); across["teams"][1]["characters"][0]["id"] = 1; variants.append(across)
        for data in variants:
            self._assert_status(422, self._save, schemas.ChampionTeamsUpsert.model_validate(data))
        with self.assertRaises(ValidationError):
            schemas.ChampionTeamsUpsert.model_validate({"teams": [{"team_number": 1, "characters": [{"id": None}]}]})
        self.assertEqual(self.db.query(models.DeckSet).count(), 0)

    def test_idempotent_resave_reuses_deck_set_replaces_teams_and_commits_once(self):
        first = schemas.ChampionTeamsResponse.model_validate(self._save())
        with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
            second = schemas.ChampionTeamsResponse.model_validate(self._save(self._payload(offset=25)))
        self.assertEqual(second.deck_set_id, first.deck_set_id)
        self.assertEqual(self.db.query(models.Player).count(), 3)
        self.assertEqual(self.db.query(models.DeckSet).filter_by(player_id=self.player.id).count(), 1)
        self.assertEqual(self.db.query(models.DeckTeam).count(), 5)
        self.assertEqual(second.teams[0].character_ids, [26, 27, 28, 29, 30])
        commit.assert_called_once_with()

    def test_failed_resave_rolls_back_and_preserves_old_complete_deck(self):
        original = schemas.ChampionTeamsResponse.model_validate(self._save())
        with patch.object(self.db, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaises(RuntimeError):
                self._save(self._payload(offset=25))
        current = schemas.ChampionTeamsResponse.model_validate(
            main.get_champion_teams(self.champion.id, self.player.id, self.db, self.owner)
        )
        self.assertEqual(current.deck_set_id, original.deck_set_id)
        self.assertEqual(current.teams[0].character_ids, [1, 2, 3, 4, 5])
        self.assertEqual(self.db.query(models.DeckTeam).count(), 5)

    def test_save_cache_invalidation_and_failure_boundary(self):
        key = main._dashboard_cache_key(self.champion.id, "stats")
        main._dashboard_cache[key] = {"value": {}, "expires_at": float("inf")}
        self._save()
        self.assertNotIn(key, main._dashboard_cache)
        with patch.object(main, "invalidate_dashboard_cache", side_effect=RuntimeError("cache failed")), patch("builtins.print") as log:
            response = schemas.ChampionTeamsResponse.model_validate(self._save(self._payload(offset=25)))
        self.assertEqual(response.status, "complete")
        self.assertIn(f"tournament={self.champion.id}", log.call_args.args[0])

    def test_save_scope_membership_and_permissions(self):
        self._assert_status(409, main.save_champion_teams, self.full.id, self.full_player.id, self._payload(), self.db, self.owner)
        self._assert_status(404, main.save_champion_teams, self.champion.id, self.other_player.id, self._payload(), self.db, self.owner)
        self._assert_status(403, main.save_champion_teams, self.champion.id, self.player.id, self._payload(), self.db, self.other)
        self._assert_status(401, main.save_champion_teams, self.champion.id, self.player.id, self._payload(), self.db, None)
        response = self._save(user=self.admin)
        self.assertEqual(response["status"], "complete")

    def test_get_distinguishes_not_saved_incomplete_and_complete(self):
        empty = schemas.ChampionTeamsResponse.model_validate(
            main.get_champion_teams(self.champion.id, self.player.id, self.db, self.owner)
        )
        self.assertEqual((empty.status, empty.deck_set_id, empty.teams), ("not_saved", None, []))
        deck_set = models.DeckSet(player_id=self.player.id)
        self.db.add(deck_set); self.db.flush()
        self.db.add(models.DeckTeam(deck_set_id=deck_set.id, team_number=1, char1_id=1))
        self.db.commit()
        incomplete = schemas.ChampionTeamsResponse.model_validate(
            main.get_champion_teams(self.champion.id, self.player.id, self.db, self.owner)
        )
        self.assertEqual(incomplete.status, "incomplete")
        complete = schemas.ChampionTeamsResponse.model_validate(self._save())
        self.assertEqual(complete.status, "complete")

    def test_get_scope_permissions_and_other_tournament_player(self):
        self._assert_status(409, main.get_champion_teams, self.full.id, self.full_player.id, self.db, self.owner)
        self._assert_status(404, main.get_champion_teams, self.champion.id, self.other_player.id, self.db, self.owner)
        self._assert_status(403, main.get_champion_teams, self.champion.id, self.player.id, self.db, self.other)
        self._assert_status(401, main.get_champion_teams, self.champion.id, self.player.id, self.db, None)

    def test_analyze_checks_authorization_before_form_parsing(self):
        request = FakeRequest([self._upload()])
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.analyze_champion_deck(self.champion.id, self.player.id, request, self.db, self.other))
        self.assertEqual(raised.exception.status_code, 403)
        self.assertFalse(request.form_called)

    def test_analyze_one_and_five_images_null_seed_no_db_write_and_cleanup(self):
        for count in (1, 5):
            request = FakeRequest([self._upload(content=f"image-{index}".encode()) for index in range(count)])
            observed_paths = []
            def fake_process(paths, tournament_id, reference, **kwargs):
                observed_paths.extend(paths)
                self.assertEqual(reference, self.player.id)
                self.assertTrue(kwargs["include_source_metadata"])
                intermediate = Path(self.upload_directory.name) / "generated-crop.png"
                intermediate.write_bytes(b"crop")
                kwargs["created_output_paths"].append(str(intermediate))
                character = {
                    "predicted_character_id": None,
                    "confidence": 0,
                    "image_url": str(intermediate.resolve()),
                    "template_source_url": "/api/uploads/cropped/generated-crop.png",
                }
                return {"suggested_teams": [[dict(character) for _ in range(5)] for _ in range(5)]}
            with patch.object(main, "process_images", side_effect=fake_process):
                result = asyncio.run(main.analyze_champion_deck(self.champion.id, self.player.id, request, self.db, self.owner))
            self.assertIsNone(result["suggested_seed"])
            self.assertEqual([team["team_number"] for team in result["teams"]], [1, 2, 3, 4, 5])
            self.assertTrue(result["teams"][0]["characters"][0]["unresolved"])
            self.assertTrue(all(not Path(path).exists() for path in observed_paths))
            self.assertNotIn(str(Path(self.upload_directory.name).resolve()), str(result))
            self.assertNotIn("generated-crop.png", str(result))
            self.assertEqual(self.db.query(models.DeckSet).count(), 0)

    def test_analyze_rejects_image_count_mime_empty_and_cleans_on_analysis_error(self):
        for images in ([], [self._upload() for _ in range(6)]):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.analyze_champion_deck(self.champion.id, self.player.id, FakeRequest(images), self.db, self.owner))
            self.assertEqual(raised.exception.status_code, 422)
        for upload in (self._upload(content_type="text/plain"), self._upload(content=b"")):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.analyze_champion_deck(self.champion.id, self.player.id, FakeRequest([upload]), self.db, self.owner))
            self.assertEqual(raised.exception.status_code, 422)
        paths = []
        def fail(paths_arg, *args, **kwargs):
            paths.extend(paths_arg)
            intermediate = Path(self.upload_directory.name) / "failed-crop.png"
            intermediate.write_bytes(b"crop")
            paths.append(str(intermediate))
            kwargs["created_output_paths"].append(str(intermediate))
            raise RuntimeError("analysis failed")
        with patch.object(main, "process_images", side_effect=fail):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.analyze_champion_deck(self.champion.id, self.player.id, FakeRequest([self._upload()]), self.db, self.owner))
        self.assertEqual(raised.exception.status_code, 500)
        self.assertTrue(all(not Path(path).exists() for path in paths))

    def test_save_collapses_preexisting_multiple_deck_sets_for_champion_player(self):
        first = models.DeckSet(player_id=self.player.id)
        second = models.DeckSet(player_id=self.player.id)
        unrelated = models.DeckSet(player_id=self.other_player.id)
        self.db.add_all([first, second, unrelated])
        self.db.flush()
        self.db.add_all([
            models.DeckTeam(deck_set_id=first.id, team_number=1, char1_id=1),
            models.DeckTeam(deck_set_id=second.id, team_number=1, char1_id=2),
            models.DeckTeam(deck_set_id=unrelated.id, team_number=1, char1_id=3),
        ])
        self.db.commit()

        response = schemas.ChampionTeamsResponse.model_validate(self._save())
        self.assertEqual(response.deck_set_id, first.id)
        self.assertEqual(
            self.db.query(models.DeckSet).filter_by(player_id=self.player.id).count(),
            1,
        )
        self.assertEqual(self.db.query(models.DeckTeam).count(), 6)
        self.assertEqual(
            self.db.query(models.DeckSet).filter_by(player_id=self.other_player.id).count(),
            1,
        )
        self.assertEqual(
            self.db.query(models.DeckTeam).filter_by(deck_set_id=unrelated.id).count(),
            1,
        )

    def test_analyze_scope_membership_and_routes(self):
        cases = ((409, self.full.id, self.full_player.id, self.owner), (404, self.champion.id, self.other_player.id, self.owner), (401, self.champion.id, self.player.id, None))
        for status, tournament_id, player_id, user in cases:
            request = FakeRequest([self._upload()])
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.analyze_champion_deck(tournament_id, player_id, request, self.db, user))
            self.assertEqual(raised.exception.status_code, status)
            self.assertFalse(request.form_called)
        expected = {
            ("POST", "/api/tournaments/{tournament_id}/players/by-id/{player_id}/analyze-deck", main.analyze_champion_deck),
            ("PUT", "/api/tournaments/{tournament_id}/players/by-id/{player_id}/teams", main.save_champion_teams),
            ("GET", "/api/tournaments/{tournament_id}/players/by-id/{player_id}/teams", main.get_champion_teams),
        }
        routes = {(method, route.path, route.endpoint) for route in main.app.routes for method in (getattr(route, "methods", None) or set())}
        self.assertTrue(expected <= routes)


if __name__ == "__main__":
    unittest.main()
