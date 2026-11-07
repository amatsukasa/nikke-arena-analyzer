from pathlib import Path
from io import BytesIO
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from sqlalchemy import create_engine, text, event
from services.player_icons import encode_webp, decode_icon, InvalidIcon, IconTooLarge
from scripts import migrate_player_icons as migration


def png(size=(108, 108)):
    im = Image.new('RGBA', size)
    im.putdata([((x*13)%256,(y*17)%256,70,(x*255)//max(1,size[0]-1))
                for y in range(size[1]) for x in range(size[0])])
    stream = BytesIO(); im.save(stream, 'PNG'); return stream.getvalue()


class CodecTests(unittest.TestCase):
    def test_png_and_webp_preserve_dimensions_and_exact_alpha(self):
        source = png()
        for data in [source, encode_webp(source)]:
            output = encode_webp(data)
            self.assertEqual(Image.open(BytesIO(output)).format, 'WEBP')
            self.assertEqual(decode_icon(output).size, (108,108))
            self.assertEqual(decode_icon(source).getchannel('A').tobytes(),
                             decode_icon(output).getchannel('A').tobytes())

    def test_corrupt_truncated_and_oversized_inputs(self):
        for data in [b'', b'not image', png()[:40]]:
            with self.assertRaises(InvalidIcon): encode_webp(data)
        with patch('services.player_icons.MAX_PIXELS', 100):
            with self.assertRaises(IconTooLarge): encode_webp(png())


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base/'uploads'/'player_icons'; self.root.mkdir(parents=True)
        self.backup = self.base/'external-backup'
        self.engine = create_engine('sqlite:///'+str(self.base/'test.db'))
        with self.engine.begin() as c:
            c.execute(text('CREATE TABLE players (id INTEGER PRIMARY KEY, tournament_id INTEGER, icon_url TEXT)'))
        self.source = self.root/'tournament_1'/'seed_1.png'; self.source.parent.mkdir()
        self.source.write_bytes(png())
        self.url = migration.PREFIX+'tournament_1/seed_1.png'
        with self.engine.begin() as c:
            c.execute(text('INSERT INTO players VALUES (1,1,:url)'),dict(url=self.url))

    def tearDown(self):
        self.engine.dispose(); self.temp.cleanup()

    def prepare(self):
        migration.backup(self.engine,self.root,self.backup)
        return migration.verify_backup(self.root,self.backup,True)

    def row(self): return migration.rows(self.engine)[0]

    def test_dry_run_has_no_db_file_or_lock_changes(self):
        before={str(p.relative_to(self.base)):p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        report=migration.run(self.engine,self.root)
        after={str(p.relative_to(self.base)):p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        self.assertEqual(before,after); self.assertEqual(report['success'],1)
        self.assertEqual(self.row()['icon_url'],self.url)

    def test_migrate_resume_idempotence_and_separate_cleanup(self):
        self.prepare()
        result=migration.run(self.engine,self.root,self.backup,True)
        self.assertEqual(result['success'],1); self.assertTrue(self.source.exists())
        self.assertTrue(self.source.with_suffix('.webp').exists())
        repeat=migration.run(self.engine,self.root,self.backup,True)
        self.assertEqual(repeat['already_webp'],1)
        manifest=migration.verify_backup(self.root,self.backup)
        self.assertEqual(migration.cleanup(self.engine,self.root,self.backup,manifest)[0]['status'],'would_delete')
        self.assertTrue(self.source.exists())
        migration.cleanup(self.engine,self.root,self.backup,manifest,True)
        self.assertFalse(self.source.exists())
        self.assertEqual(migration.run(self.engine,self.root,self.backup,True)['already_webp'],1)

    def test_db_failure_leaves_png_and_retry_recovers_installed_webp(self):
        manifest=self.prepare(); row=self.row()
        def fail_update(conn,cursor,statement,parameters,context,executemany):
            if statement.startswith('UPDATE players'): raise RuntimeError('injected failure')
        event.listen(self.engine,'before_cursor_execute',fail_update)
        try:
            with self.assertRaises(RuntimeError):
                migration.migrate_one(self.engine,self.root,row,self.backup,manifest,True)
        finally: event.remove(self.engine,'before_cursor_execute',fail_update)
        self.assertEqual(self.row()['icon_url'],self.url)
        self.assertTrue(self.source.exists()); self.assertTrue(self.source.with_suffix('.webp').exists())
        self.assertEqual(migration.run(self.engine,self.root,self.backup,True)['success'],1)

    def test_file_and_db_concurrent_updates_are_not_overwritten(self):
        manifest=self.prepare(); row=self.row()
        def change_file(): self.source.write_bytes(png((69,69)))
        with self.assertRaisesRegex(ValueError,'Concurrent file'):
            migration.migrate_one(self.engine,self.root,row,self.backup,manifest,True,before_install=change_file)
        self.source.write_bytes(png())
        def change_db():
            with self.engine.begin() as c: c.execute(text("UPDATE players SET icon_url='new-url' WHERE id=1"))
        with self.assertRaisesRegex(ValueError,'Concurrent DB'):
            migration.migrate_one(self.engine,self.root,row,self.backup,manifest,True,before_install=change_db)
        self.assertFalse(self.source.with_suffix('.webp').exists())

    def test_external_verified_backup_is_required(self):
        with self.assertRaises(ValueError): migration.external(self.root,self.root/'backup')
        migration.backup(self.engine,self.root,self.backup)
        with self.assertRaises(ValueError): migration.verify_backup(self.root,self.backup)
        migration.verify_backup(self.root,self.backup,True)
        (self.backup/'files'/'tournament_1'/'seed_1.png').write_bytes(b'bad')
        with self.assertRaises(ValueError): migration.verify_backup(self.root,self.backup)

    def test_orphans_wrong_tournament_and_destination_conflicts(self):
        orphan=self.source.parent/'seed_2.png';orphan.write_bytes(png())
        self.prepare()
        report=migration.run(self.engine,self.root)
        self.assertEqual(report['unreferenced_png'],['tournament_1/seed_2.png'])
        with self.assertRaises(ValueError): migration.relative_url(self.url,2)
        self.source.with_suffix('.webp').write_bytes(b'foreign target')
        self.assertEqual(migration.run(self.engine,self.root,self.backup,True)['failed'],1)
        self.assertEqual(self.row()['icon_url'],self.url)

    def test_free_space_and_retained_budget_stop_before_db_update(self):
        manifest=self.prepare()
        with patch.object(migration.shutil,'disk_usage',return_value=type('Usage',(),dict(free=0))()):
            with self.assertRaisesRegex(ValueError,'free space'):
                migration.migrate_one(self.engine,self.root,self.row(),self.backup,manifest,True)
        with self.assertRaisesRegex(ValueError,'budget'):
            migration.migrate_one(self.engine,self.root,self.row(),self.backup,manifest,True,max_retained=1)
        self.assertEqual(self.row()['icon_url'],self.url)

    def test_cleanup_refuses_changed_source_or_target(self):
        manifest=self.prepare();migration.run(self.engine,self.root,self.backup,True)
        self.source.write_bytes(b'updated')
        result=migration.cleanup(self.engine,self.root,self.backup,manifest,True)
        self.assertEqual(result[0]['status'],'skipped');self.assertTrue(self.source.exists())

    def test_resume_after_batch_limit_and_query_string(self):
        with self.engine.begin() as c:
            c.execute(text('UPDATE players SET icon_url=:url'),dict(url=self.url+'?v=123'))
        second=self.source.parent/'seed_2.png';second.write_bytes(png((69,69)))
        with self.engine.begin() as c:
            c.execute(text('INSERT INTO players VALUES (2,1,:url)'),dict(url=migration.PREFIX+'tournament_1/seed_2.png'))
        self.prepare()
        self.assertEqual(migration.run(self.engine,self.root,self.backup,True,limit=1,batch_size=1)['success'],1)
        report=migration.run(self.engine,self.root,self.backup,True,after_id=1)
        self.assertEqual(report['success'],1)
        self.assertEqual(migration.run(self.engine,self.root,self.backup,True)['already_webp'],2)

    def test_rollback_after_png_cleanup_restores_original_and_db(self):
        manifest=self.prepare();original=self.source.read_bytes()
        migration.run(self.engine,self.root,self.backup,True)
        migration.cleanup(self.engine,self.root,self.backup,manifest,True)
        self.assertFalse(self.source.exists())
        self.assertEqual(migration.rollback(self.engine,self.root,self.backup,manifest)[0]['status'],'would_restore')
        self.assertFalse(self.source.exists())
        result=migration.rollback(self.engine,self.root,self.backup,manifest,True)
        self.assertEqual(result[0]['status'],'restored')
        self.assertEqual(self.source.read_bytes(),original)
        self.assertEqual(self.row()['icon_url'],self.url)
        self.assertTrue(self.source.with_suffix('.webp').exists())
        self.assertEqual(migration.rollback(self.engine,self.root,self.backup,manifest,True),[])

    def test_rollback_refuses_newer_upload_and_cleanup_protects_deck_reference(self):
        manifest=self.prepare();migration.run(self.engine,self.root,self.backup,True)
        with self.engine.begin() as c:
            c.execute(text('CREATE TABLE deck_sets (image_path TEXT)'))
            c.execute(text('INSERT INTO deck_sets VALUES (:url)'),dict(url=self.url))
        self.assertEqual(migration.cleanup(self.engine,self.root,self.backup,manifest,True)[0]['status'],'skipped')
        self.source.with_suffix('.webp').write_bytes(encode_webp(png((69,69))))
        self.assertEqual(migration.rollback(self.engine,self.root,self.backup,manifest,True)[0]['status'],'skipped')
        self.assertTrue(self.row()['icon_url'].endswith('.webp'))

    def test_repeated_small_batches_advance_without_cursor(self):
        second=self.source.parent/'seed_2.png';second.write_bytes(png((69,69)))
        with self.engine.begin() as c:
            c.execute(text('INSERT INTO players VALUES (2,1,:url)'),dict(url=migration.PREFIX+'tournament_1/seed_2.png'))
        self.prepare()
        self.assertEqual(migration.run(self.engine,self.root,self.backup,True,limit=1)['success'],1)
        self.assertEqual(migration.run(self.engine,self.root,self.backup,True,limit=1)['success'],1)
        self.assertEqual(migration.run(self.engine,self.root,self.backup,True)['already_webp'],2)

    def test_cleanup_loads_reference_snapshot_once_per_batch(self):
        self.prepare();migration.run(self.engine,self.root,self.backup,True)
        with patch.object(migration,'rows',wraps=migration.rows) as query:
            migration.cleanup(self.engine,self.root,self.backup,migration.verify_backup(self.root,self.backup))
        self.assertLessEqual(query.call_count,1)

    def test_4748_icons_batched_migration_cleanup_query_count_and_capacity(self):
        import time
        raw=png((69,69)); encoded=encode_webp(raw)
        self.source.write_bytes(raw)
        with self.engine.begin() as c:
            c.execute(text('INSERT INTO players (id,tournament_id,icon_url) VALUES (:id,1,:url)'),
                      [dict(id=i,url=migration.PREFIX+f'tournament_1/seed_{i}.png') for i in range(2,4749)])
        for i in range(2,4749): (self.source.parent/f'seed_{i}.png').write_bytes(raw)
        manifest=self.prepare();start=time.perf_counter();queries=[]
        def count(conn,cursor,statement,parameters,context,many):
            if statement.startswith('SELECT'):queries.append(statement)
        event.listen(self.engine,'before_cursor_execute',count)
        try:
            # Actual 32MiB boundary: reserve all but one encoded image with a
            # pre-existing PNG/WebP pair, outside the DB migration candidates.
            reserve=self.source.parent/'seed_99999.png';reserve.write_bytes(raw)
            reserve.with_suffix('.webp').write_bytes(b'x'*(32*1024*1024-len(encoded)))
            with patch.object(migration,'encode_webp',return_value=encoded):
                first=migration.run(self.engine,self.root,self.backup,True,limit=100)
                self.assertTrue(first['stopped_for_capacity']);self.assertEqual(first['success'],1)
                self.assertLessEqual(migration.retained_bytes(self.root),32*1024*1024)
                migration.cleanup(self.engine,self.root,self.backup,manifest,True)
                self.assertTrue(reserve.exists())
                reserve.unlink();reserve.with_suffix('.webp').unlink()
                while True:
                    report=migration.run(self.engine,self.root,self.backup,True,limit=500)
                    self.assertEqual(report['failed'],0)
                    if report['success']==0:break
            before=len(queries);deleted=0
            while True:
                batch=migration.cleanup(self.engine,self.root,self.backup,manifest,True,limit=500)
                if not batch:break
                self.assertEqual(len({x['source'] for x in batch}),len(batch))
                self.assertTrue(all(x['status']=='deleted' for x in batch));deleted+=len(batch)
            self.assertEqual(deleted,4747)
            self.assertLess(len(queries)-before,60)
            self.assertEqual(len(list(self.root.glob('tournament_*/*.webp'))),4748)
            print('BULK_4748 seconds=',round(time.perf_counter()-start,2),'selects=',len(queries),'cleanup_selects=',len(queries)-before)
        finally:event.remove(self.engine,'before_cursor_execute',count)


if __name__=='__main__': unittest.main()
