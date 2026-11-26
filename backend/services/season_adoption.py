"""Weapon slot shares and rankings for Summary."""

from collections import Counter

from services import arena_phases, registration_adoption


WEAPONS = ("AR", "MG", "RL", "SG", "SMG", "SR")


def measure(count, population):
    return {"count": count, "population": population,
            "rate": registration_adoption.trends_rate(count, population) if population else None}


def stage_slot_counts(db, bulk, ids, stage):
    selected = set(ids)
    players = [p.id for p in bulk.get("players", ()) if p.tournament_id in selected]
    decks = arena_phases.phase_deck_sets(db, players, stage) if players else []
    if stage == "legacy":
        # Old saves replace one set. Multiple retained sets have no authoritative version.
        sets_per_player = Counter(deck.player_id for deck in decks)
        decks = [deck for deck in decks if sets_per_player[deck.player_id] == 1]
    return Counter(
        cid for deck in decks for team in deck.teams for cid in registration_adoption.slot_ids(team)
        if type(cid) is int and cid > 0 and cid != registration_adoption.EMPTY_SLOT
    )


def weapon_statistics(db, bulk, groups, stages, catalog):
    weapons_by_id = {cid: c.weapon for cid, c in catalog.items() if c.weapon in WEAPONS}
    by_stage = {}
    overall = Counter()
    for stage in stages:
        slots = stage_slot_counts(db, bulk, groups[stage], stage)
        weapon_counts = Counter()
        for cid, count in slots.items():
            weapon_counts[weapons_by_id.get(cid, "unknown")] += count
        by_stage[stage] = {"slots": sum(slots.values()),
                           "counts": {weapon: weapon_counts[weapon] for weapon in (*WEAPONS, "unknown")}}
        overall.update(slots)

    total = sum(overall.values())
    rankings = {weapon: [] for weapon in WEAPONS}
    for cid, count in sorted(overall.items(), key=lambda row: (-row[1], row[0])):
        weapon = weapons_by_id.get(cid)
        if weapon and len(rankings[weapon]) < 5:
            rankings[weapon].append({"id": cid, "name": catalog[cid].name, **measure(count, total)})
    return {"by_stage": by_stage, "slots": total, "rankings": rankings}
