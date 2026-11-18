"""Championship is canonical. Legacy tournament columns are read-only fallback data."""
import hashlib
import json
from fastapi import HTTPException
import models

DEFAULTS = {"deck_registration_phases": False, "is_champion_arena": False, "include_in_statistics": True}
LEGACY = {"deck_registration_phases": "legacy_deck_registration_phases", "is_champion_arena": "legacy_is_champion_arena", "include_in_statistics": "legacy_has_match_data"}
FIELDS = frozenset(DEFAULTS)


def children(db, title_id, lock=False):
    query = db.query(models.Tournament).filter_by(championship_id=title_id).order_by(models.Tournament.id)
    return (query.populate_existing().with_for_update(of=models.Tournament) if lock else query).all()


def describe(title, tournaments):
    rows = [{"id": row.id, "title": row.name, **{key: getattr(row, "has_match_data" if key == "include_in_statistics" else key) for key in DEFAULTS}} for row in tournaments]
    stored = {key: getattr(title, key) for key in DEFAULTS}
    values, conflicts, inherited = {}, [], []
    for key, default in DEFAULTS.items():
        if stored[key] is not None:
            values[key] = stored[key]
            continue
        inherited.append(key)
        observed = {getattr(row, LEGACY[key]) for row in tournaments}
        if None in observed or len(observed) > 1:
            values[key] = None
            conflicts.append(key)
        else:
            values[key] = next(iter(observed), default)
    revision = hashlib.sha256(json.dumps({"stored": stored, "display_order": title.display_order, "rows": rows}, sort_keys=True).encode()).hexdigest()
    return {**values, "display_order": title.display_order, "configuration_conflicts": conflicts, "inherited_settings": inherited,
            "linked_tournaments": rows, "settings_revision": revision}


def require_resolved(title, tournaments):
    state = describe(title, tournaments)
    if state["configuration_conflicts"] or state["inherited_settings"]:
        raise HTTPException(409, "Title settings are unresolved; ask an administrator to review and save them first")


def save(db, title, request, tournaments):
    changes = {key: getattr(request, key) for key in FIELDS & request.model_fields_set}
    if not changes:
        return []
    state = describe(title, tournaments)
    if request.settings_revision != state["settings_revision"]:
        raise HTTPException(409, "Title or linked tournaments changed; reload before saving")
    if state["configuration_conflicts"] and not FIELDS <= changes.keys():
        raise HTTPException(409, "Review the conflicting tournaments and select all three settings")
    effective_field = {"include_in_statistics": "has_match_data"}
    changed = [row for row in tournaments if any(getattr(row, effective_field.get(key, key)) != value for key, value in changes.items())]
    if changed and not request.apply_to_existing:
        raise HTTPException(409, "Confirm applying these settings to all linked tournaments")
    ensure_history_visible(db, tournaments, changes)
    for key, value in changes.items():
        setattr(title, key, value)
    # Do NOT synchronize or edit legacy columns. Every reader resolves the title.
    return [row.id for row in tournaments]


def ensure_history_visible(db, tournaments, changes):
    """Reject disabling transitions, including legacy data; never mutate records."""
    phase_ids = [row.id for row in tournaments if changes.get("deck_registration_phases") is False and row.deck_registration_phases is True]
    hidden_ids = [row.id for row in tournaments if
        (changes.get("include_in_statistics") is False and row.has_match_data is True) or
        (changes.get("is_champion_arena") is False and row.is_champion_arena is True)]
    ids = set(phase_ids) | set(hidden_ids)
    if not ids:
        return
    phase_history = (db.query(models.ArenaDeckRegistration.id).filter(models.ArenaDeckRegistration.tournament_id.in_(ids)).first()
                     or db.query(models.ArenaMatchRevision.id).filter(models.ArenaMatchRevision.tournament_id.in_(ids)).first())
    if phase_history:
        raise HTTPException(409, "Phase history exists; settings cannot disable or hide linked data")
    if hidden_ids:
        legacy_history = (db.query(models.Match.id).filter(models.Match.tournament_id.in_(hidden_ids)).first()
            or db.query(models.DeckSet.id).join(models.Player, models.Player.id == models.DeckSet.player_id).filter(models.Player.tournament_id.in_(hidden_ids)).first()
            or db.query(models.TournamentSnapshot.id).filter(models.TournamentSnapshot.tournament_id.in_(hidden_ids)).first())
        if legacy_history or any(row.id in hidden_ids and row.publication_status == "published" for row in tournaments):
            raise HTTPException(409, "Legacy history or published data exists; settings cannot hide linked data")
