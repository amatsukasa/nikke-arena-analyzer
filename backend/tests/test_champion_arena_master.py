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
    def test_master_creation_and_public_ordering(self):
        main.create_champion_arena_tournament(schemas.ChampionArenaTournamentBase(title="Season 1",display_order=37,is_champion_arena=True,has_match_data=False),self.admin,self.db)
        main.create_champion_arena_tournament(schemas.ChampionArenaTournamentBase(title="任意の過去大会",display_order=36,is_champion_arena=True,has_match_data=False),self.admin,self.db)
        main.create_champion_arena_tournament(schemas.ChampionArenaTournamentBase(title="順序未設定",display_order=None,game_start_date=date(2026,1,1),is_champion_arena=True,has_match_data=False),self.admin,self.db)
        self.db.add(models.Tournament(name="対象外",date=date.today(),is_champion_arena=False,has_match_data=False))
        self.db.commit()
        rows=main.get_champion_arena_tournaments(self.db)
        self.assertEqual([row["title"] for row in rows],["Season 1","任意の過去大会","順序未設定"])
        self.assertTrue(all(row["has_match_data"] is False for row in rows))
    def test_public_tournament_list_hides_master_only_rows(self):
        self.db.add(models.Tournament(name="master",date=date.today(),is_champion_arena=True,has_match_data=False,publication_status="published"))
        self.db.commit()
        self.assertEqual(main.get_tournaments(False,self.db,None),[])
    def test_normal_tournament_creation_defaults_to_match_data(self):
        tournament=main.create_tournament(
            schemas.TournamentBase(name="通常大会",date=date(2026,2,1)),self.db,self.admin
        )
        self.assertTrue(tournament.has_match_data)
    def test_admin_writes_keep_shared_admin_authorization(self):
        for endpoint, parameter in (
            (main.create_champion_arena_tournament,"admin"),
            (main.update_champion_arena_tournament,"_"),
        ):
            dependency=inspect.signature(endpoint).parameters[parameter].default
            self.assertIs(dependency.dependency,auth_module.require_admin)

if __name__=="__main__": unittest.main()
