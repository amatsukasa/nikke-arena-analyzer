"""Keep the private-name-first registration path independent of deck and image uploads."""

from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from auth import create_access_token
from database import Base, get_db


class PrivatePlayerNamesTest(TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine, autoflush=False)
        with self.sessions.begin() as db:
            db.add_all([
                models.AppUser(id=1, email="owner@example.test", hashed_password="unused", role="contributor", approval_status="active"),
                models.AppUser(id=2, email="other@example.test", hashed_password="unused", role="contributor", approval_status="active"),
                models.Championship(id=1, name="Official", deck_registration_phases=True),
                models.Tournament(id=1, name="Draft", date=date(2026, 11, 21), championship_id=1, created_by=1),
                models.Tournament(id=2, name="Published", date=date(2026, 11, 21), championship_id=1, created_by=1, publication_status="published"),
                models.Tournament(id=3, name="Eight", date=date(2026, 11, 21), championship_id=1, registration_scope="champion_8", created_by=1),
                models.Tournament(id=4, name="Published legacy", date=date(2026, 11, 21),
                                  created_by=1, publication_status="published"),
                models.Player(id=20, tournament_id=2, seed_number=1, name=main.automatic_player_name(1)),
                models.Player(id=40, tournament_id=4, seed_number=1, name=main.automatic_player_name(1)),
                models.Player(id=30, tournament_id=3, champion_slot=1, seed_number=4, name=main.automatic_player_name(4)),
                *(models.Character(id=cid, name=f"Nikke {cid}") for cid in range(1, 26)),
            ])

        def test_db():
            with self.sessions() as db:
                yield db

        root = self.enterContext(TemporaryDirectory())
        self.icons = Path(root) / "player_icons"
        self.enterContext(patch.object(main, "PLAYER_ICONS_DIR", self.icons))
        self.enterContext(patch.dict(main.app.dependency_overrides, {get_db: test_db}))
        self.owner = self.client(1)
        self.other = self.client(2)
        self.reader = self.client()

    def client(self, user_id=None):
        headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"} if user_id else {}
        client = TestClient(main.app, headers=headers)
        self.addCleanup(client.close)
        return client

    def register_name(self, name, *, seed=5, tournament=1):
        return self.owner.put(f"/api/tournaments/{tournament}/private-player-names",
                              json={"seed_number": seed, "private_name": name})

    def upload_icon(self, tournament, seed):
        image = BytesIO()
        Image.new("RGB", (35, 35), (45, 75, 100)).save(image, format="PNG")
        return self.owner.post("/api/upload/player-icon",
                               data={"tournament_id": str(tournament), "seed_number": str(seed)},
                               files={"image": ("icon.png", image.getvalue(), "image/png")})

    def test_name_first_keeps_the_same_player_for_icon_and_decks(self):
        # Warm the bracket before the placeholder Player is created.
        bracket_path = "/api/tournaments/1/bracket"
        self.assertEqual(self.owner.get(bracket_path).status_code, 200)
        first = self.register_name("  Private test name  ")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.headers["Cache-Control"], "private, no-store")
        row = first.json()
        self.assertEqual(row["private_name"], "Private test name")
        self.assertTrue(row["created"])
        with self.sessions() as db:
            player = db.get(models.Player, row["id"])
            self.assertEqual(player.name, main.automatic_player_name(5))
            self.assertIsNone(player.icon_url)
            self.assertEqual(db.query(models.ArenaDeckRegistration).count(), 0)
            self.assertEqual(db.query(models.DeckSet).count(), 0)
        bracket = self.owner.get(bracket_path)
        self.assertNotIn("Private test name", bracket.text)
        players = [player for group in bracket.json()["groups"] for player in group["players"] if player]
        self.assertTrue(any(player["id"] == row["id"] and not player["has_deck"] for player in players))

        uploaded = self.upload_icon(1, 5)
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(uploaded.json()["player_id"], row["id"])
        teams = [
            {"team_number": i + 1, "characters": [{"id": cid} for cid in range(5 * i + 1, 5 * i + 6)]}
            for i in range(5)
        ]
        deck = self.owner.post("/api/tournaments/1/teams", json={"seed_number": 5, "teams": teams})
        self.assertEqual(deck.status_code, 200, deck.text)
        with self.sessions() as db:
            players = db.query(models.Player).filter_by(tournament_id=1, seed_number=5).all()
            self.assertEqual([(player.id, player.private_name, player.icon_url) for player in players],
                             [(row["id"], "Private test name", uploaded.json()["url"])])
            self.assertEqual(db.query(models.ArenaDeckRegistration).filter_by(player_id=row["id"]).count(), 1)

    def test_blank_and_published_empty_seed_cannot_create_a_player(self):
        self.assertEqual(self.register_name("  ").status_code, 404)
        self.assertEqual(self.register_name("Invalid seed", seed=0).status_code, 422)
        self.assertEqual(self.register_name("Invalid seed", seed=65).status_code, 422)
        self.assertEqual(self.register_name("Private", seed=5, tournament=2).status_code, 409)
        self.assertEqual(self.register_name("Published alias", seed=1, tournament=2).status_code, 409)
        self.assertEqual(self.register_name(None, seed=1, tournament=2).status_code, 409)
        with self.sessions() as db:
            self.assertEqual(db.query(models.Player).filter_by(seed_number=5).count(), 0)

    def assert_published(self, response):
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["code"], "tournament_published")

    def test_publication_blocks_seed_writes_on_existing_and_empty_seeds(self):
        for tournament in (2, 4):
            for seed in (1, 5):
                with self.subTest(tournament=tournament, seed=seed):
                    path = f"/api/tournaments/{tournament}"
                    self.assert_published(self.upload_icon(tournament, seed))
                    self.assert_published(self.owner.post(f"{path}/players/{seed}", json={}))
                    self.assert_published(self.owner.post(f"{path}/teams", json={"seed_number": seed, "teams": []}))
                    self.assert_published(self.register_name("Private", seed=seed, tournament=tournament))
                    self.assertFalse((self.icons / f"tournament_{tournament}" / f"seed_{seed}.webp").exists())
            with self.sessions() as db:
                players = db.query(models.Player).filter_by(tournament_id=tournament).all()
                self.assertEqual([player.seed_number for player in players], [1])
                self.assertIsNone(players[0].icon_url)
                self.assertIsNone(players[0].private_name)

    def test_icon_first_and_reupload_reuse_the_same_unpublished_seed(self):
        first = self.upload_icon(1, 64)
        self.assertEqual(first.status_code, 200, first.text)
        updated = self.upload_icon(1, 64)
        self.assertEqual(updated.json()["player_id"], first.json()["player_id"])
        named = self.register_name("Private", seed=64)
        self.assertEqual(named.status_code, 200, named.text)
        self.assertFalse(named.json()["created"])
        self.assertEqual(named.json()["id"], first.json()["player_id"])
        with self.sessions() as db:
            players = db.query(models.Player).filter_by(tournament_id=1).all()
            self.assertEqual([(player.seed_number, player.private_name) for player in players], [(64, "Private")])

    def test_published_champion_player_profile_icon_and_teams_are_locked(self):
        with self.sessions.begin() as db:
            db.get(models.Tournament, 3).publication_status = "published"
        path = "/api/tournaments/3"
        self.assert_published(self.owner.put(f"{path}/private-player-names",
                                             json={"player_id": 30, "private_name": "Private"}))
        image = BytesIO()
        Image.new("RGB", (35, 35), (45, 75, 100)).save(image, format="PNG")
        player = f"{path}/players/by-id/30"
        self.assert_published(self.owner.put(f"{player}/icon", files={"image": ("icon.png", image.getvalue(), "image/png")}))
        self.assert_published(self.owner.delete(f"{player}/icon"))
        self.assert_published(self.owner.put(f"{player}/teams", json={"teams": []}))
        self.assertEqual(self.owner.get(player).status_code, 200)

        with self.sessions.begin() as db:
            db.get(models.Tournament, 3).publication_status = "draft"
        allowed = self.owner.put(f"{path}/private-player-names", json={"player_id": 30, "private_name": "Private"})
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_seed_writers_cannot_create_an_out_of_range_or_champion_slotless_player(self):
        self.assertEqual(self.upload_icon(1, 65).status_code, 422)
        self.assertEqual(self.owner.post("/api/tournaments/1/players/0", json={}).status_code, 422)
        self.assertEqual(self.owner.post("/api/tournaments/1/teams", json={"seed_number": -1, "teams": []}).status_code, 422)
        self.assertEqual(self.upload_icon(3, 4).status_code, 422)
        self.assertEqual(self.owner.post("/api/tournaments/3/players/5", json={}).status_code, 422)
        with self.sessions() as db:
            self.assertEqual(db.query(models.Player).filter_by(tournament_id=1).count(), 0)
            self.assertEqual(db.query(models.Player).filter_by(tournament_id=3).count(), 1)

    def test_name_writes_are_scoped_to_the_manager_and_existing_champion_slot(self):
        path = "/api/tournaments/1/private-player-names"
        body = {"seed_number": 5, "private_name": "Private"}
        self.assertEqual(self.other.put(path, json=body).status_code, 403)
        self.assertEqual(self.reader.put(path, json=body).status_code, 401)
        self.assertEqual(self.other.get(path).status_code, 403)
        self.assertEqual(self.reader.get(path).status_code, 401)
        self.assertEqual(self.register_name("Private", tournament=3).status_code, 422)
        path = "/api/tournaments/3/private-player-names"
        known = self.owner.put(path, json={"player_id": 30, "private_name": "Existing"})
        self.assertEqual(known.status_code, 200, known.text)
        self.assertFalse(known.json()["created"])
        self.assertEqual(self.owner.put(path, json={"player_id": 999, "private_name": "Missing"}).status_code, 404)
