from datetime import date
import inspect, os, sys, unittest
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
BACKEND=Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path: sys.path.insert(0,str(BACKEND))
from database import Base,SessionLocal,engine
import main,models,schemas
import auth as auth_module

class ChampionArenaMasterTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine); Base.metadata.create_all(engine); self.db=SessionLocal()
        self.admin=models.AppUser(email="admin@example.invalid",hashed_password="x",role="admin",approval_status="active")
        self.db.add(self.admin); self.db.commit(); self.db.refresh(self.admin)
    def tearDown(self): self.db.close()
    def _title(self, name="Season 1", **values):
        settings = dict(deck_registration_phases=False, is_champion_arena=True, include_in_statistics=True)
        settings.update(values)
        result = main.create_championship(schemas.ChampionshipCreate(name=name, date=date(2026, 1, 1), **settings), self.db, self.admin)
        return self.db.get(models.Championship, result["id"])

    def test_master_creation_and_public_ordering(self):
        past = self._title("Past")
        latest = self._title("Season 1")
        self._title("Excluded", is_champion_arena=False)
        for index in range(2):
            self.db.add(models.Tournament(name=f"Dataset {index}", date=date.today(), championship_id=latest.id))
        self.db.commit()
        rows = main.get_champion_arena_tournaments(self.db)
        self.assertEqual([row["title"] for row in rows], ["Season 1", "Past"])
        self.assertEqual([row["id"] for row in rows], [f"championship:{latest.id}", f"championship:{past.id}"])

    def test_public_tournament_list_hides_master_only_rows(self):
        title = self._title(include_in_statistics=False)
        self.db.add(models.Tournament(name="master", date=date.today(), championship_id=title.id, publication_status="published"))
        self.db.commit()
        self.assertEqual(main.get_tournaments(False, self.db, None), [])

    def test_normal_tournament_creation_defaults_to_match_data(self):
        title = self._title()
        tournament = main.create_tournament(schemas.TournamentBase(name="Normal", date=date(2026, 2, 1), championship_id=title.id), self.db, self.admin)
        self.assertTrue(tournament.has_match_data)
        self.assertTrue(tournament.is_champion_arena)

    def test_personal_result_settings_and_links_keep_analysis_unchanged(self):
        legacy = models.Tournament(name="Legacy label", date=date(1970, 1, 1), display_order=1,
                                   legacy_is_champion_arena=True, legacy_has_match_data=False)
        self.db.add(legacy)
        self.db.commit()
        older = self._title("Older")
        older.display_order = 2
        self.db.commit()
        created = main.create_championship(schemas.ChampionshipCreate(
            name="Renamed title", display_order=3, arena_results_enabled=True,
            is_champion_arena=False, include_in_statistics=False,
            arena_result_legacy_tournament_ids=[legacy.id],
        ), self.db, self.admin)
        title_id = created["id"]
        self.assertEqual(created["arena_result_legacy_tournament_ids"], [legacy.id])
        self.assertFalse(created["is_champion_arena"])
        self.assertFalse(created["include_in_statistics"])
        self.db.refresh(legacy)
        self.assertIsNone(legacy.championship_id)
        self.assertFalse(legacy.has_match_data)
        self.assertEqual(legacy.publication_status, "draft")
        events = main.get_champion_arena_tournaments(self.db)
        self.assertEqual([row["title"] for row in events], ["Renamed title", "Older"])
        self.assertEqual(events[0]["legacy_tournament_ids"], [legacy.id])
        with self.assertRaises(main.HTTPException) as error:
            main.update_championship(older.id, schemas.ChampionshipCreate(
                name=older.name, arena_result_legacy_tournament_ids=[legacy.id],
            ), self.db, self.admin)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(main.get_tournaments(False, self.db, None), [])

    def test_real_title_link_uses_tournament_id_without_matching_names(self):
        title = self._title("Same name")
        linked = models.Tournament(name="Different name", date=date.today(), championship_id=title.id,
                                    legacy_is_champion_arena=True)
        unlinked = models.Tournament(name=title.name, date=date.today(), legacy_is_champion_arena=True)
        self.db.add_all([linked, unlinked])
        self.db.commit()
        rows = {row["id"]: row for row in main.get_champion_arena_tournaments(self.db)}
        self.assertEqual(rows[f"championship:{title.id}"]["legacy_tournament_ids"], [linked.id])
        self.assertIn(f"legacy-tournament:{unlinked.id}", rows)
        title.arena_results_enabled = False
        self.db.commit()
        self.assertEqual([row["id"] for row in main.get_champion_arena_tournaments(self.db)],
                         [f"legacy-tournament:{unlinked.id}"])

    def test_existing_tournament_can_join_and_leave_results_without_losing_match_data(self):
        title = self._title(is_champion_arena=False)
        tournament = models.Tournament(name="Beta37", date=date(2026, 3, 1), championship_id=title.id, created_by=self.admin.id, publication_status="published")
        self.db.add(tournament)
        self.db.commit()
        main.update_championship(title.id, schemas.ChampionshipCreate(
            name=title.name, arena_results_enabled=True,
        ), self.db, self.admin)
        self.assertEqual([row["id"] for row in main.get_champion_arena_tournaments(self.db)], [f"championship:{title.id}"])
        self.assertEqual([row.id for row in main.get_tournaments(False, self.db, None)], [tournament.id])
        main.update_championship(title.id, schemas.ChampionshipCreate(
            name=title.name, arena_results_enabled=False,
        ), self.db, self.admin)
        self.assertEqual(main.get_champion_arena_tournaments(self.db), [])
        self.assertTrue(tournament.has_match_data)
        self.assertFalse(tournament.is_champion_arena)
        self.assertEqual(tournament.publication_status, "published")

    def test_legacy_partial_update_preserves_champion_arena_fields(self):
        title = self._title()
        start = date(2026, 3, 1)
        tournament = models.Tournament(name="Before", date=date(2026, 3, 2), championship_id=title.id, created_by=self.admin.id, display_order=37, game_start_date=start)
        self.db.add(tournament)
        self.db.commit()
        updated = main.update_tournament(tournament.id, schemas.TournamentUpdate(name="After"), self.db, self.admin)
        self.assertEqual(updated.display_order, 37)
        self.assertTrue(updated.is_champion_arena)
        self.assertTrue(updated.has_match_data)
        self.assertEqual(updated.game_start_date, start)
    def test_admin_writes_keep_shared_admin_authorization(self):
        for endpoint, parameter in (
            (main.create_champion_arena_tournament,"admin"),
            (main.update_champion_arena_tournament,"_"),
        ):
            dependency=inspect.signature(endpoint).parameters[parameter].default
            self.assertIs(dependency.dependency,auth_module.require_admin)

if __name__=="__main__": unittest.main()
