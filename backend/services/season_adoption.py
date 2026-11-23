"""Stage adoption and season comparisons for the public Summary."""

from collections import Counter, defaultdict
from fractions import Fraction

from sqlalchemy import func, select

import models
from services import arena_phases, registration_adoption


WEAPONS = ("SG", "SR", "AR", "MG", "RL", "SMG")
BURSTS = ("1", "2", "3")
EMPTY_SLOT = registration_adoption.EMPTY_SLOT
slot_ids = registration_adoption.slot_ids


def previous_season(db, title, formal):
    """Resolve the immediately preceding arena title before looking for public data."""
    if not formal:
        return None, None, None
    championship, tournament = models.Championship, models.Tournament
    rows = db.execute(select(
        championship.id, championship.name, championship.display_order,
        func.coalesce(championship.deck_registration_phases, tournament.legacy_deck_registration_phases).label("phased"),
        func.coalesce(championship.is_champion_arena, tournament.legacy_is_champion_arena).label("arena"),
        championship.arena_results_enabled,
    ).select_from(championship).outerjoin(tournament, tournament.championship_id == championship.id).distinct()).all()
    formats, candidates = defaultdict(set), {}
    for row in rows:
        formats[row.id].add(row.phased)
        if row.arena or row.phased or row.arena_results_enabled or row.id == title.id:
            candidates[row.id] = row
    if title.display_order is None or any(row.display_order is None for row in candidates.values()):
        return None, None, "order_unknown"
    if formats[title.id] != {True}:
        return None, None, "format_unknown"
    if sum(row.display_order == title.display_order for row in candidates.values()) != 1:
        return None, None, "order_unknown"
    earlier = [row for row in candidates.values() if row.display_order < title.display_order]
    if not earlier:
        return None, None, "no_previous_season"
    last_order = max(row.display_order for row in earlier)
    previous = [row for row in earlier if row.display_order == last_order]
    if len(previous) != 1:
        return None, None, "order_unknown"
    predecessor = previous[0]
    phase_format = formats[predecessor.id]
    if phase_format == {True}:
        return "growth", predecessor, None
    if phase_format == {False} and all(formats[row.id] == {False} for row in earlier):
        return "transition", predecessor, None
    return None, None, "format_unknown"


def registered_slots(team):
    return [cid for cid in slot_ids(team) if isinstance(cid, int) and cid > 0 and cid != EMPTY_SLOT]


def measure(count, population):
    return {"count": count, "population": population,
            "rate": registration_adoption.trends_rate(count, population) if population else None}


def difference(current, previous):
    if not current["population"] or not previous["population"]:
        return None
    return 100 * (Fraction(current["count"], current["population"]) -
                  Fraction(previous["count"], previous["population"]))


def comparison(current, previous):
    delta = difference(current, previous)
    return {"current": current, "previous": previous,
            "change_pt": round(float(delta), 1) if delta is not None else None}


def weapon_usage(decks, catalog):
    slots, users = Counter(), Counter()
    population = set()
    for deck in decks:
        if not deck.teams:
            continue
        population.add(deck.player_id)
        weapons = set()
        for team in deck.teams:
            for cid in registered_slots(team):
                character = catalog.get(cid)
                weapon = character.weapon if character and character.weapon in WEAPONS else None
                slots[weapon] += 1
                if weapon:
                    weapons.add(weapon)
        users.update(weapons)
    total_slots = sum(slots.values())
    return {
        "commanders": len(population), "slots": total_slots, "unknown_slots": slots[None],
        "weapons": [{"weapon": weapon, "slots": measure(slots[weapon], total_slots),
                     "commanders": measure(users[weapon], len(population))} for weapon in WEAPONS],
    }


def players_in(bulk, ids):
    selected = set(ids)
    return [p for p in bulk.get("players", ()) if p.tournament_id in selected]


def stage_weapons(db, bulk, ids, stage, catalog):
    players = players_in(bulk, ids)
    decks = arena_phases.phase_deck_sets(db, [p.id for p in players], stage) if players else []
    if stage == "legacy":
        # Legacy saves replace the sole set. Multiple coexisting sets are ambiguous.
        sets_per_player = Counter(deck.player_id for deck in decks)
        decks = [deck for deck in decks if sets_per_player[deck.player_id] == 1]
    return weapon_usage(decks, catalog)


def first_registration_cohort(db, bulk, ids, formal, catalog):
    players = players_in(bulk, ids)
    legacy = arena_phases.legacy_teams_by_player(players, db)
    legacy_counts = Counter(deck.player_id for deck in bulk.get("decks", ()))
    first = {}
    if formal:
        for revision in bulk.get("registrations", ()):
            if revision.tournament_id in ids and revision.phase == "initial":
                first.setdefault(revision.player_id, revision)
    decks, represented = [], set()
    for player in players:
        # A retained legacy set predates the append-only initial revisions.
        if legacy_counts[player.id]:
            teams = legacy[player.id]
        else:
            revision = first.get(player.id)
            teams = revision.teams if revision and revision.qualification == "initial" else []
        if not arena_phases.complete(teams) or any(
            slot["id"] == EMPTY_SLOT for team in teams for slot in team["characters"]
        ):
            continue
        decks.append(arena_phases.projected_deck(player.id, teams, -player.id))
        represented.add(player.tournament_id)
    return {"tournaments": len(represented), "public_tournaments": len(ids), **weapon_usage(decks, catalog)}


def migration_weapons(db, bulk, current_ids, prior_ids, catalog):
    current = first_registration_cohort(db, bulk, current_ids, True, catalog)
    previous = first_registration_cohort(db, bulk, prior_ids, False, catalog)

    def scope(cohort):
        return {**{key: value for key, value in cohort.items() if key != "weapons"},
                "reason": ("no_public_tournaments" if not cohort["public_tournaments"] else
                           "no_complete_registrations" if not cohort["commanders"] else None)}

    return {"current": scope(current), "previous": scope(previous), "weapons": [
        {"weapon": row["weapon"], **{metric: comparison(row[metric], before[metric])
                                   for metric in ("slots", "commanders")}}
        for row, before in zip(current["weapons"], previous["weapons"])
    ]}


def burst_rankings(trends, catalog):
    adoption = trends.get("character_usage_by_result", {}).get("all", {})
    population = trends["total_players"]
    ranked = {burst: [] for burst in BURSTS}
    for row in adoption.get("characters", ()):
        character = catalog.get(row["id"])
        burst = character.burst_phase if character else None
        for group in BURSTS if burst == "A" else (burst,):
            if group in ranked and len(ranked[group]) < 5:
                ranked[group].append({"id": row["id"], "name": row["name"], **measure(row["count"], population)})
    return {"population": population, "groups": ranked}


def growth_rows(entries, previous_counts, current_population, previous_population):
    rows = []
    for key, identity, count in entries:
        current = measure(count, current_population)
        previous = measure(previous_counts.get(key, 0), previous_population)
        delta = difference(current, previous)
        if delta > 0:
            rows.append((delta, key, {**identity, **comparison(current, previous)}))
    rows.sort(key=lambda row: (-row[0], row[1]))
    return [row for _, _, row in rows[:5]]


def stage_growth(db, bulk, prior_ids, stage, trends, catalog, debut_ids):
    decks = registration_adoption.trends_decks(db, players_in(bulk, prior_ids), stage) if prior_ids else []
    population = len({deck.player_id for deck in decks})
    current = trends["total_players"]
    result = {"current_population": current, "previous_population": population,
              "previous_tournaments": len(prior_ids), "characters": [], "teams": []}
    if not current or not population:
        return result
    characters, teams, _, _ = registration_adoption.trends_usage(decks, catalog)
    char_entries = ((row["id"], {"id": row["id"], "name": row["name"]}, row["count"])
                    for row in trends["character_usage_by_result"]["all"]["characters"]
                    if row["id"] not in debut_ids)
    team_entries = []
    for row in trends["team_usage"]:
        key = row["canonical_id"]
        ids = [int(cid) for cid in key.split(",")]
        if len(set(ids)) == 5 and ids[0] > 0 and EMPTY_SLOT not in ids:
            team_entries.append((key, {"canonical_id": key, "character_ids": ids}, row["player_count"]))
    return {**result, "characters": growth_rows(char_entries, {key: len(users) for key, users in characters.items()},
                                                current, population),
            "teams": growth_rows(team_entries, {key: len(users) for key, users in teams.items()}, current, population)}
