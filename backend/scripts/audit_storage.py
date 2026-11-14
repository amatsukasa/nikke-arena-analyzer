"""Read-only logical byte inventory. Does not decode, migrate, lock or delete images."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, inspect, text
from database_safety import normalize_postgresql_driver_url
from scripts.migrate_player_icons import NAME, relative_url, rows

CATEGORIES = ('referenced_player_png', 'protected_legacy_player_png', 'orphan_player_png',
              'unsupported_referenced_player_png', 'player_webp', 'cropped', 'templates',
              'temporary_or_hidden', 'other')

def upload_relative(value):
    value = value.partition('?')[0]
    for prefix in ('/api/uploads/', '/app/uploads/', 'uploads/'):
        if value.startswith(prefix):
            path = value[len(prefix):]
            if not PurePosixPath(path).is_absolute() and '..' not in PurePosixPath(path).parts:
                return path
    return None

def audit(engine, root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('An existing, non-symlink uploads root is required')
    root = root.resolve()
    players = rows(engine)
    valid_png, all_references, legacy_references = set(), set(), set()
    unsupported_urls = 0
    for row in players:
        value = row['icon_url']
        path = upload_relative(value)
        if path: all_references.add(path)
        try:
            relative = relative_url(value, row['tournament_id'])
            if relative.endswith('.png'): valid_png.add('player_icons/'+relative)
        except ValueError:
            unsupported_urls += 1
    if inspect(engine).has_table('deck_sets'):
        with engine.connect() as connection:
            if engine.dialect.name == 'postgresql': connection.execute(text('SET TRANSACTION READ ONLY'))
            for value in connection.execute(text('SELECT image_path FROM deck_sets WHERE image_path IS NOT NULL')).scalars():
                path = upload_relative(value)
                if path: legacy_references.add(path)
    counts = {name: dict(files=0, bytes=0) for name in CATEGORIES}
    seen, errors, links = set(), [], 0
    def unreadable(error):
        errors.append('directory_unreadable')
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=unreadable):
        for name in list(dirs):
            if (Path(directory)/name).is_symlink():
                links += 1; dirs.remove(name)
        for name in files:
            path=Path(directory)/name
            if path.is_symlink(): links += 1; continue
            relative=path.relative_to(root).as_posix()
            try:
                if not path.is_file(): errors.append('non_regular_file'); continue
                size=path.stat().st_size
            except OSError:
                errors.append('file_unreadable'); continue
            seen.add(relative)
            parts=PurePosixPath(relative).parts
            if any(p.startswith('.') for p in parts) or name.endswith(('.tmp','.bak','.recovery.json')):
                category='temporary_or_hidden'
            elif parts[0]=='templates': category='templates'
            elif parts[0] in ('cropped','debug_match'): category='cropped' if parts[0]=='cropped' else 'other'
            elif parts[0]=='player_icons' and path.suffix.lower()=='.png':
                canonical=bool(NAME.fullmatch(relative[len('player_icons/'):]))
                if relative in valid_png: category='referenced_player_png'
                elif relative in all_references: category='unsupported_referenced_player_png'
                elif relative in legacy_references: category='protected_legacy_player_png'
                elif canonical: category='orphan_player_png'
                else: category='other'
            elif parts[0]=='player_icons' and path.suffix.lower()=='.webp': category='player_webp'
            else: category='other'
            counts[category]['files']+=1; counts[category]['bytes']+=size
    return dict(read_only=True, complete=not errors and not links, units='logical bytes (not disk allocation; hard links count per path)',
                categories=counts, total_files=sum(v['files'] for v in counts.values()),
                total_bytes=sum(v['bytes'] for v in counts.values()),
                migration_candidate_bytes=counts['referenced_player_png']['bytes'],
                out_of_scope_bytes=sum(v['bytes'] for k,v in counts.items() if k!='referenced_player_png'),
                candidate_with_legacy_reference_count=len(valid_png & legacy_references),
                missing_player_reference_count=len(all_references-seen), unsupported_player_urls=unsupported_urls,
                symlinks_excluded=links, errors=errors,
                note='Candidates still require backup, image decode, hash and DB checks; not a deletion approval.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    engine=None
    try:
        raw=os.environ.get('ICON_MIGRATION_DATABASE_URL')
        if not raw: raise ValueError('ICON_MIGRATION_DATABASE_URL required')
        engine=create_engine(normalize_postgresql_driver_url(raw))
        result=audit(engine,args.root)
        print(json.dumps(result,indent=2,ensure_ascii=True))
        return 0 if result['complete'] else 2
    except Exception as exc:
        print(json.dumps(dict(error=type(exc).__name__,message='Read-only audit stopped; verify root, DB and permissions.')))
        return 2
    finally:
        if engine is not None: engine.dispose()

if __name__=='__main__': raise SystemExit(main())
