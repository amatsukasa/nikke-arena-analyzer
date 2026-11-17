"""Bounded phase-aware read cache shared by public aggregate endpoints.

PostgreSQL row versions are checked on every request, including in other workers.
Nothing is persisted and legacy snapshots never become phase-aware by assumption.
"""
from collections import OrderedDict
from copy import deepcopy
import json
import threading
from contextlib import nullcontext

from sqlalchemy import bindparam, text

_cache = OrderedDict()
_cache_guard = threading.RLock()
_build_locks = [threading.RLock() for _ in range(16)]
_build_context = threading.local()
_MAX_BYTES = 64 * 1024 * 1024
_MAX_ENTRY_BYTES = 16 * 1024 * 1024
_MAX_ENTRIES = 32

# Only row identities/versions leave PostgreSQL; private names and images do not.
# Unlike max(id)/timestamps this also detects in-place edits and deletes.
_VERSION_SQL = text("""
WITH selected AS (SELECT id FROM tournaments WHERE id IN :ids),
versions AS (
 SELECT 't' AS kind, t.id, t.xmin::text AS version FROM tournaments t JOIN selected s ON s.id=t.id
 UNION ALL SELECT 'p', p.id, p.xmin::text FROM players p JOIN selected s ON s.id=p.tournament_id
 UNION ALL SELECT 'd', d.id, d.xmin::text FROM deck_sets d JOIN players p ON p.id=d.player_id JOIN selected s ON s.id=p.tournament_id
 UNION ALL SELECT 'dt', dt.id, dt.xmin::text FROM deck_teams dt JOIN deck_sets d ON d.id=dt.deck_set_id JOIN players p ON p.id=d.player_id JOIN selected s ON s.id=p.tournament_id
 UNION ALL SELECT 'm', m.id, m.xmin::text FROM matches m JOIN selected s ON s.id=m.tournament_id
 UNION ALL SELECT 'r', r.id, r.xmin::text FROM round_results r JOIN matches m ON m.id=r.match_id JOIN selected s ON s.id=m.tournament_id
 UNION ALL SELECT 'ar', r.id, r.xmin::text FROM arena_deck_registrations r JOIN selected s ON s.id=r.tournament_id
 UNION ALL SELECT 'am', r.id, r.xmin::text FROM arena_match_revisions r JOIN selected s ON s.id=r.tournament_id
 UNION ALL SELECT 's', t.id, t.xmin::text FROM tournament_snapshots t JOIN selected s ON s.id=t.tournament_id
 UNION ALL SELECT 'c', c.id, c.xmin::text FROM characters c
)
SELECT md5(coalesce(string_agg(kind || ':' || id::text || ':' || version, ',' ORDER BY kind,id), '')) FROM versions
""").bindparams(bindparam('ids', expanding=True))


def clear_cache():
    with _cache_guard:
        _cache.clear()


def cached(db, tournament_ids, phase, kind, compute):
    """Cache JSON-compatible detached values, never ORM objects/authorization."""
    if db.bind.dialect.name != 'postgresql' or db.new or db.dirty or db.deleted:
        return compute()
    ids = tuple(sorted(set(tournament_ids)))
    if not ids:
        return compute()
    key = (str(db.bind.url), ids, phase, kind)
    # A stripe also prevents concurrent stats/list requests rebuilding one scope.
    # A combined all-stages entry may reuse stage/metadata entries. Nested
    # reads still use the guarded cache, but cannot hold a second build stripe.
    lock = nullcontext() if getattr(_build_context, "depth", 0) else _build_locks[hash(key) % len(_build_locks)]
    with lock:
        previous_depth = getattr(_build_context, "depth", 0)
        _build_context.depth = previous_depth + 1
        try:
            return _cached_value(db, ids, key, compute)
        finally:
            _build_context.depth = previous_depth


def _cached_value(db, ids, key, compute):
    version = db.execute(_VERSION_SQL, {'ids': ids}).scalar_one()
    with _cache_guard:
        entry = _cache.get(key)
        if entry is not None and entry[0] == version:
            _cache.move_to_end(key)
            return deepcopy(entry[1])
    value = compute()
    # Do not publish a cache entry assembled across concurrent DB commits.
    if db.execute(_VERSION_SQL, {'ids': ids}).scalar_one() != version:
        return value
    size = len(json.dumps(value, ensure_ascii=False, default=str).encode())
    if size <= _MAX_ENTRY_BYTES:
        with _cache_guard:
            _cache[key] = (version, deepcopy(value), size)
            _cache.move_to_end(key)
            while len(_cache) > _MAX_ENTRIES or sum(e[2] for e in _cache.values()) > _MAX_BYTES:
                _cache.popitem(last=False)
    return value
