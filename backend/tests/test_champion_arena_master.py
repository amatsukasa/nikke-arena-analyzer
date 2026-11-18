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

    def _save(self, title, **changes):
        from services import championship_settings
        state = championship_settings.describe(title, championship_settings.children(self.db, title.id))
        values = {key: state[key] for key in championship_settings.FIELDS}
        values.update(changes)
        return main.update_championship(title.id, schemas.ChampionshipCreate(name=title.name, settings_revision=state["settings_revision"], apply_to_existing=True, **values), self.db, self.admin)

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

    def test_existing_tournament_can_join_and_leave_results_without_losing_match_data(self):
        title = self._title(is_champion_arena=False)
        tournament = models.Tournament(name="Beta37", date=date(2026, 3, 1), championship_id=title.id, created_by=self.admin.id, publication_status="published")
        self.db.add(tournament)
        self.db.commit()
        self._save(title, is_champion_arena=True)
        self.assertEqual([row["id"] for row in main.get_champion_arena_tournaments(self.db)], [f"championship:{title.id}"])
        self.assertEqual([row.id for row in main.get_tournaments(False, self.db, None)], [tournament.id])
        self._save(title, is_champion_arena=False)
        self.assertEqual(main.get_champion_arena_tournaments(self.db), [])
        self.assertTrue(tournament.has_match_data)
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
