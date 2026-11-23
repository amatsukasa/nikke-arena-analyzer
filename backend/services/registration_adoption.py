"""Registration populations and identities shared by Trends and Summary."""

from collections import Counter, defaultdict

from services import arena_phases, team_statistics_display


EMPTY_SLOT = 9999


def slot_ids(team):
    return [getattr(team, f"char{slot}_id", None) for slot in range(1, 6)]


def trends_decks(db, players, stage):
    return [deck for deck in arena_phases.phase_deck_sets(db, [p.id for p in players], stage)
            if len(deck.teams) == 5]


def trends_usage(decks, characters):
    character_users, team_users = defaultdict(set), defaultdict(set)
    occurrences, first_orders = Counter(), {}
    for deck in decks:
        for team in deck.teams:
            key = team_statistics_display.canonical(team)
            if not key:
                continue
            ids = slot_ids(team)
            for cid in (set(ids) - {EMPTY_SLOT}) & characters.keys():
                character_users[cid].add(deck.player_id)
            team_users[key].add(deck.player_id)
            occurrences[key] += 1
            first_orders.setdefault(key, ids)
    return character_users, team_users, occurrences, first_orders


def trends_rate(count, population):
    return round(count / population * 100, 1) if population else 0
