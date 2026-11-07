"""Offline player-icon migration. Default is read-only audit/dry-run.

Never imports main/database or starts the app. Credentials come only from env.
The external backup is immutable; the append-only journal enables recovery.
"""
from contextlib import nullcontext
from pathlib import Path
from hashlib import sha256
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.player_icons import encode_webp, decode_icon, icon_mutation_lock
from database_safety import normalize_postgresql_driver_url
from sqlalchemy import create_engine, text, inspect

NAME = re.compile(r"^tournament_(\d+)/(?:seed|player)_\d+\.(png|webp)$")
PREFIX = "/api/uploads/player_icons/"


def digest(data):
    return sha256(data).hexdigest()


def safe_path(root, relative):
    if not NAME.fullmatch(relative):
        raise ValueError("Unsupported icon path")
    p = root / relative
    if p.is_symlink() or p.parent.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
        raise ValueError("Unsafe icon path")
    return p


def relative_url(url, tournament):
    if not url or not url.startswith(PREFIX):
        raise ValueError("Unsupported icon URL")
    relative = url[len(PREFIX):].partition("?")[0]
    m = NAME.fullmatch(relative)
    if not m or int(m.group(1)) != tournament:
        raise ValueError("Icon belongs to another tournament or path is invalid")
    return relative


def rows(engine):
    with engine.connect() as c:
        if engine.dialect.name == "postgresql":
            c.execute(text("SET TRANSACTION READ ONLY"))
        return [dict(r) for r in c.execute(text(
            "SELECT id,tournament_id,icon_url FROM players WHERE icon_url IS NOT NULL ORDER BY id"
        )).mappings()]


def additional_references(engine):
    """Legacy deck image references are protected, never implicitly migrated."""
    if not inspect(engine).has_table("deck_sets"):
        return set()
    with engine.connect() as c:
        if engine.dialect.name == "postgresql":
            c.execute(text("SET TRANSACTION READ ONLY"))
        values = c.execute(text("SELECT image_path FROM deck_sets WHERE image_path IS NOT NULL")).scalars()
        result = set()
        for value in values:
            value = value.partition("?")[0]
            for prefix in (PREFIX, "/app/uploads/player_icons/", "uploads/player_icons/"):
                if value.startswith(prefix):
                    result.add(value[len(prefix):])
        return result


def inventory(root):
    result = {}
    for p in root.glob("tournament_*/*.png"):
        relative = p.relative_to(root).as_posix()
        try:
            checked = safe_path(root, relative)
            result[relative] = dict(sha256=digest(checked.read_bytes()), bytes=checked.stat().st_size)
        except (ValueError, OSError):
            continue
    return result


def external(root, path):
    path = Path(path).resolve()
    # All of uploads, not merely player_icons, is considered the source Volume.
    if path.is_relative_to(root.parent.resolve()) or root.parent.resolve().is_relative_to(path):
        raise ValueError("Backup must be outside the uploads tree")
    return path


def manifest_bytes(manifest):
    return json.dumps(manifest, sort_keys=True, ensure_ascii=True).encode()


def backup(engine, root, directory):
    directory = external(root, directory)
    if directory.exists():
        raise ValueError("Backup directory must not already exist")
    snapshot = rows(engine)
    files = inventory(root)
    directory.mkdir(parents=True)
    for relative, entry in files.items():
        source = safe_path(root, relative)
        data = source.read_bytes()
        if digest(data) != entry['sha256']:
            raise ValueError("Source changed during backup; discard this incomplete backup")
        target = safe_path(directory / 'files', relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = dict(version=1, files=files, players=snapshot)
    (directory / 'manifest.json').write_bytes(manifest_bytes(manifest))
    return dict(backed_up=len(files))


def verify_backup(root, directory, write_marker=False):
    directory = external(root, directory)
    raw = (directory / 'manifest.json').read_bytes()
    manifest = json.loads(raw)
    if manifest.get('version') != 1:
        raise ValueError("Unsupported backup version")
    for relative, entry in manifest['files'].items():
        data = safe_path(directory / 'files', relative).read_bytes()
        if digest(data) != entry['sha256']:
            raise ValueError("Backup hash mismatch")
        decode_icon(data)
    if write_marker:
        # Rehearse actual restoration outside the Volume before certifying backup.
        with tempfile.TemporaryDirectory(prefix='icon-restore-', dir=directory.parent) as tmp:
            for relative, entry in manifest['files'].items():
                restored = safe_path(Path(tmp), relative)
                restored.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(safe_path(directory / 'files', relative), restored)
                if digest(restored.read_bytes()) != entry['sha256']:
                    raise ValueError("Restore verification failed")
    marker = directory / 'verified.json'
    if write_marker:
        marker.write_text(json.dumps(dict(manifest_sha256=digest(raw))), encoding='utf-8')
    elif not marker.exists() or json.loads(marker.read_text())['manifest_sha256'] != digest(raw):
        raise ValueError("Run verify-backup --execute first")
    return manifest


def journal(directory, entry):
    # Intents are durable before installing a target; success is logged after commit.
    with (directory / 'migration.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=True) + '\n')
        f.flush()
        os.fsync(f.fileno())


def retained_bytes(root):
    return sum(p.with_suffix('.webp').stat().st_size for p in root.glob('tournament_*/*.png')
               if not p.with_suffix('.webp').is_symlink() and not p.is_symlink() and not p.parent.is_symlink() and p.with_suffix('.webp').is_file())


def migrate_one(engine, root, row, directory, manifest, execute=False,
                min_free=64*1024*1024, max_retained=32*1024*1024, before_install=None, capacity_state=None, lock_held=False):
    relative = relative_url(row['icon_url'], row['tournament_id'])
    if relative.endswith('.webp'):
        decode_icon(safe_path(root, relative).read_bytes())
        return dict(status='already_webp')
    source = safe_path(root, relative)
    data = source.read_bytes()
    original_hash = digest(data)
    encoded = encode_webp(data)
    target_relative = relative[:-4] + '.webp'
    target = safe_path(root, target_relative)
    target_hash = digest(encoded)
    details = dict(id=row['id'], old_url=row['icon_url'], new_url=PREFIX+target_relative,
                   source=relative, target=target_relative, source_sha256=original_hash,
                   target_sha256=target_hash, before=len(data), after=len(encoded))
    if not execute:
        return dict(status='would_migrate', **details)
    entry = manifest['files'].get(relative)
    snapshot = next((r for r in manifest['players'] if r['id'] == row['id']), None)
    if not entry or entry['sha256'] != original_hash or not snapshot or snapshot['icon_url'] != row['icon_url']:
        raise ValueError("Current file/reference is not covered by the verified backup")
    if before_install:
        before_install()
    with nullcontext() if lock_held else icon_mutation_lock(root):
        # Required ordering: filesystem lock, then DB row lock (same as API).
        with engine.begin() as c:
            suffix = ' FOR UPDATE' if engine.dialect.name == 'postgresql' else ''
            current = c.execute(text('SELECT icon_url,tournament_id FROM players WHERE id=:id'+suffix),
                                dict(id=row['id'])).mappings().first()
            if not current or current['icon_url'] != row['icon_url'] or current['tournament_id'] != row['tournament_id']:
                raise ValueError("Concurrent DB update detected")
            if digest(source.read_bytes()) != original_hash:
                raise ValueError("Concurrent file update detected")
            if target.exists() and digest(target.read_bytes()) != target_hash:
                raise ValueError("Destination conflict; not overwriting")
            if not target.exists():
                if shutil.disk_usage(root).free < min_free + len(encoded):
                    raise ValueError("Insufficient free space; stop and review PNG cleanup")
                if (capacity_state['retained'] if capacity_state is not None else retained_bytes(root)) + len(encoded) > max_retained:
                    raise ValueError("Retained double-storage budget reached; review PNG cleanup")
            journal(directory, dict(state='intent', **details))
            if not target.exists():
                temporary = target.parent / ('.'+target.name+'.'+uuid.uuid4().hex+'.tmp')
                try:
                    with temporary.open('xb') as f:
                        f.write(encoded); f.flush(); os.fsync(f.fileno())
                    if digest(source.read_bytes()) != original_hash:
                        raise ValueError("Source changed during conversion")
                    os.replace(temporary, target)
                    if capacity_state is not None:
                        capacity_state['retained'] += len(encoded)
                finally:
                    temporary.unlink(missing_ok=True)
            updated = c.execute(text('UPDATE players SET icon_url=:new WHERE id=:id AND icon_url=:old'),
                                dict(new=details['new_url'], id=row['id'], old=row['icon_url']))
            if updated.rowcount != 1:
                raise ValueError("Concurrent reference update detected")
        # On DB failure PNG and old URL stay intact; validated WebP may remain.
        # A retry accepts only this exact output, and safely completes the update.
        journal(directory, dict(state='committed', **details))
    return dict(status='migrated', **details)


def cleanup(engine, root, directory, manifest, execute=False, limit=100):
    # Hold the shared writer lock for one bounded batch and take one DB snapshot.
    with icon_mutation_lock(root) if execute else nullcontext():
        return _cleanup_batch(engine, root, directory, manifest, execute, limit)


def _cleanup_batch(engine, root, directory, manifest, execute=False, limit=100):
    current = rows(engine)
    owners = {row['id']: row for row in current}
    references = set()
    for row in current:
        if row['icon_url'].startswith(PREFIX):
            references.add(relative_url(row['icon_url'], row['tournament_id']))
    extra = additional_references(engine)
    logfile = directory / 'migration.jsonl'
    entries = {}
    for line in logfile.read_text(encoding='utf-8').splitlines() if logfile.exists() else []:
        try:
            entry = json.loads(line)
            # Intents also recover a crash after commit but before journal append.
            if entry.get('state') in {'intent', 'committed'}:
                entries[entry['source']] = entry
        except (ValueError, KeyError):
            raise ValueError("Invalid journal; review before cleanup")
    results = []
    for entry in entries.values():
        if len(results) >= limit:
            break
        try:
            if not safe_path(root, entry["source"]).exists():
                continue
            def check():
                source = safe_path(root, entry['source'])
                target = safe_path(root, entry['target'])
                expected = manifest['files'].get(entry['source'])
                if not expected or expected['sha256'] != entry['source_sha256']:
                    raise ValueError('Backup coverage mismatch')
                if entry['source'] in extra:
                    raise ValueError('PNG has a legacy deck reference')
                owner = owners.get(entry['id'])
                if not owner or owner['icon_url'] != entry['new_url']:
                    raise ValueError('Current DB URL differs')
                if entry['source'] in references:
                    raise ValueError('PNG is still referenced')
                if digest(target.read_bytes()) != entry['target_sha256']:
                    raise ValueError('WebP changed since migration')
                decode_icon(target.read_bytes())
                if source.exists() and digest(source.read_bytes()) != entry['source_sha256']:
                    raise ValueError('PNG changed since backup')
                return source
            if execute:
                source = check()
                source.unlink(missing_ok=True)
            else:
                source = check()
            results.append(dict(id=entry['id'], source=entry['source'], bytes=entry['before'], status='deleted' if execute else 'would_delete'))
        except Exception as exc:
            results.append(dict(id=entry.get('id'), status='skipped', reason=type(exc).__name__))
    return results


def rollback(engine, root, directory, manifest, execute=False, limit=100):
    """Restore only unchanged migrated refs; never revert newer user uploads."""
    current = {r['id']: r for r in rows(engine)}
    result = []
    for old in manifest['players']:
        if len(result) >= limit:
            break
        try:
            relative = relative_url(old['icon_url'], old['tournament_id'])
            if not relative.endswith('.png'):
                continue
            target_relative = relative[:-4]+'.webp'
            now = current.get(old['id'])
            if not now or now['icon_url'] != PREFIX+target_relative:
                continue
            entries = []
            logfile = directory / 'migration.jsonl'
            for line in logfile.read_text(encoding='utf-8').splitlines() if logfile.exists() else []:
                entry = json.loads(line)
                if entry.get('id') == old['id'] and entry.get('source') == relative:
                    entries.append(entry)
            if not entries:
                raise ValueError('No migration intent found')
            intent = entries[-1]
            source = safe_path(root, relative)
            target = safe_path(root, target_relative)
            data = safe_path(directory/'files', relative).read_bytes()
            expected = manifest['files'][relative]['sha256']
            def check():
                if digest(data) != expected or digest(target.read_bytes()) != intent['target_sha256']:
                    raise ValueError('Backup or WebP changed; manual review required')
                if source.exists() and digest(source.read_bytes()) != expected:
                    raise ValueError('Original path has newer content')
            check()
            if execute:
                with icon_mutation_lock(root):
                    with engine.begin() as c:
                        suffix = ' FOR UPDATE' if engine.dialect.name == 'postgresql' else ''
                        value = c.execute(text('SELECT icon_url FROM players WHERE id=:id'+suffix),dict(id=old['id'])).scalar()
                        if value != now['icon_url']:
                            raise ValueError('Concurrent DB update detected')
                        check()
                        if not source.exists():
                            if shutil.disk_usage(root).free < len(data)+64*1024*1024:
                                raise ValueError('Insufficient restore space')
                            temporary = source.parent / ('.'+source.name+'.'+uuid.uuid4().hex+'.tmp')
                            try:
                                with temporary.open('xb') as f:
                                    f.write(data); f.flush(); os.fsync(f.fileno())
                                os.replace(temporary, source)
                            finally:
                                temporary.unlink(missing_ok=True)
                        c.execute(text('UPDATE players SET icon_url=:old WHERE id=:id AND icon_url=:new'),
                                  dict(old=old['icon_url'],id=old['id'],new=now['icon_url']))
                    journal(directory,dict(state='rolled_back',id=old['id'],source=relative))
            result.append(dict(id=old['id'],status='restored' if execute else 'would_restore'))
        except Exception as exc:
            result.append(dict(id=old['id'],status='skipped',reason=type(exc).__name__))
    return result


def run(engine, root, directory=None, execute=False, limit=100, batch_size=25,
        after_id=0, min_free=64*1024*1024, max_retained=32*1024*1024):
    # Bounded by limit; never cache a capacity estimate across unlocked batches.
    with icon_mutation_lock(root) if execute else nullcontext():
        return _run(engine, root, directory, execute, limit, batch_size,
                    after_id, min_free, max_retained)


def _run(engine, root, directory=None, execute=False, limit=100, batch_size=25,
        after_id=0, min_free=64*1024*1024, max_retained=32*1024*1024):
    root = Path(root).resolve()
    all_rows = rows(engine)
    files = inventory(root)
    referenced = additional_references(engine)
    for row in all_rows:
        try:
            referenced.add(relative_url(row['icon_url'], row['tournament_id']))
        except ValueError:
            pass
    manifest = verify_backup(root, directory) if execute else None
    capacity_state = dict(retained=retained_bytes(root)) if execute else None
    selected = sorted([r for r in all_rows if r['id'] > after_id],
                      key=lambda r: (r['icon_url'].partition('?')[0].endswith('.webp'), r['id']))[:limit]
    report = dict(mode='execute' if execute else 'dry-run', processed=0, success=0,
                  failed=0, already_webp=0, before=0, after=0,
                  unreferenced_png=sorted(set(files)-referenced), items=[])
    for offset in range(0, len(selected), batch_size):
        for row in selected[offset:offset+batch_size]:
            try:
                result = migrate_one(engine, root, row, Path(directory) if directory else None,
                                     manifest, execute, min_free, max_retained,
                                     capacity_state=capacity_state, lock_held=execute)
                if result['status'] == 'already_webp':
                    report['already_webp'] += 1
                else:
                    report['success'] += 1
                    report['before'] += result['before']; report['after'] += result['after']
            except Exception as exc:
                # Never print DB exceptions/DSNs or credential-bearing URLs.
                result = dict(id=row['id'], status='failed', reason=type(exc).__name__)
                if type(exc) is ValueError:
                    result['detail'] = str(exc)
                report['failed'] += 1
            if 'old_url' in result and '?' in result['old_url']:
                result = dict(result, old_url=result['old_url'].partition('?')[0]+'?[redacted]')
            report['items'].append(result); report['processed'] += 1
            if result.get('detail', '').startswith(('Insufficient free space', 'Retained double-storage')):
                report['stopped_for_capacity'] = True
                return report
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['migrate', 'backup', 'verify-backup', 'cleanup', 'rollback'], nargs='?', default='migrate')
    p.add_argument('--root', type=Path, default=Path('/app/uploads/player_icons'))
    p.add_argument('--backup-dir', type=Path)
    p.add_argument('--execute', action='store_true', help='Explicitly permit writes for this action')
    p.add_argument('--backup-export-confirmed', action='store_true', help='Confirm a durable external copy and DB backup have been restore-tested')
    p.add_argument('--maintenance-confirmed', action='store_true', help='Confirm all icon writers are paused for backup/migration/cleanup')
    p.add_argument('--approve-delete', action='store_true', help='Separate operator approval for PNG deletion')
    p.add_argument('--limit', type=int, default=100)
    p.add_argument('--batch-size', type=int, default=25)
    p.add_argument('--after-id', type=int, default=0)
    p.add_argument('--min-free-mib', type=int, default=64)
    p.add_argument('--max-retained-mib', type=int, default=32)
    args = p.parse_args()
    if args.limit < 1 or args.batch_size < 1 or args.min_free_mib < 1 or args.max_retained_mib < 1:
        p.error('Limits must be positive')
    if args.execute and not args.backup_dir:
        p.error('--execute requires --backup-dir outside the Volume')
    if args.execute and args.action != 'verify-backup' and not args.maintenance_confirmed:
        p.error('--execute requires --maintenance-confirmed')
    if args.execute and args.action in {'migrate', 'cleanup', 'rollback'} and not args.backup_export_confirmed:
        p.error('--execute requires --backup-export-confirmed')
    engine = None
    try:
        if args.action == 'verify-backup':
            manifest = verify_backup(args.root.resolve(), args.backup_dir, args.execute)
            result = dict(verified=len(manifest['files']))
        else:
            raw = os.environ.get('ICON_MIGRATION_DATABASE_URL')
            if not raw:
                raise ValueError('ICON_MIGRATION_DATABASE_URL is required')
            engine = create_engine(normalize_postgresql_driver_url(raw))
            if args.action == 'backup':
                result = backup(engine, args.root.resolve(), args.backup_dir) if args.execute else dict(
                    mode='dry-run', files=len(inventory(args.root)), players=len(rows(engine)))
            elif args.action == 'rollback':
                manifest = verify_backup(args.root.resolve(), args.backup_dir)
                result = rollback(engine, args.root.resolve(), args.backup_dir, manifest, args.execute, args.limit)
            elif args.action == 'cleanup':
                if args.execute and not args.approve_delete:
                    p.error('PNG deletion requires --execute --approve-delete after user approval')
                manifest = verify_backup(args.root.resolve(), args.backup_dir)
                result = cleanup(engine, args.root.resolve(), args.backup_dir, manifest, args.execute, args.limit)
            else:
                result = run(engine, args.root, args.backup_dir, args.execute, args.limit, args.batch_size,
                             args.after_id, args.min_free_mib*1024*1024, args.max_retained_mib*1024*1024)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if isinstance(result, list):
            return 2 if any(item.get('status') == 'skipped' for item in result) else 0
        return 2 if result.get('failed') else 0
    except Exception as exc:
        print(json.dumps(dict(error=type(exc).__name__, message='Operation stopped; inspect configuration, backup and conflicts locally.')))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
