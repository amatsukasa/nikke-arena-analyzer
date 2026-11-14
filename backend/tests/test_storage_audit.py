from pathlib import Path
import tempfile
import unittest
from sqlalchemy import create_engine,text
from scripts.audit_storage import audit

class StorageAuditTests(unittest.TestCase):
    def test_classification_totals_and_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'uploads';root.mkdir()
            engine=create_engine('sqlite:///'+str(Path(tmp)/'db.sqlite'))
            with engine.begin() as c:
                c.execute(text('CREATE TABLE players (id INTEGER,tournament_id INTEGER,icon_url TEXT)'))
                c.execute(text("INSERT INTO players VALUES (1,1,'/api/uploads/player_icons/tournament_1/seed_1.png'),(2,2,'/api/uploads/player_icons/tournament_1/seed_4.png'),(3,1,'/api/uploads/cropped/missing.png')"))
                c.execute(text('CREATE TABLE deck_sets (image_path TEXT)'))
                c.execute(text("INSERT INTO deck_sets VALUES ('/api/uploads/player_icons/tournament_1/seed_3.png')"))
            paths=['player_icons/tournament_1/seed_1.png','player_icons/tournament_1/seed_2.png','player_icons/tournament_1/seed_3.png','player_icons/tournament_1/seed_4.png','player_icons/tournament_1/seed_5.webp','cropped/face.png','templates/template.png','player_icons/.recovery.json','other.dat']
            for relative in paths:
                p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'12345')
            before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result=audit(engine,root)
            self.assertEqual(result['total_bytes'],45);self.assertEqual(result['migration_candidate_bytes'],5)
            self.assertEqual(result['out_of_scope_bytes'],40);self.assertTrue(result['complete'])
            self.assertTrue(all(x['files']==1 for x in result['categories'].values()))
            self.assertEqual(result['missing_player_reference_count'],1)
            self.assertEqual(result['unsupported_player_urls'],2)
            self.assertEqual(before,{p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()})
            engine.dispose()

    def test_symlinks_not_followed_and_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'uploads';root.mkdir();outside=Path(tmp)/'secret';outside.write_bytes(b'do not read')
            try: (root/'link').symlink_to(outside)
            except OSError: self.skipTest('symlinks unavailable')
            engine=create_engine('sqlite:///:memory:')
            with engine.begin() as c:c.execute(text('CREATE TABLE players (id INTEGER,tournament_id INTEGER,icon_url TEXT)'))
            result=audit(engine,root)
            self.assertEqual(result['total_bytes'],0);self.assertEqual(result['symlinks_excluded'],1)
            self.assertFalse(result['complete']);engine.dispose()
