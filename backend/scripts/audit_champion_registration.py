"""Read-only audit for the current champion registration schema.

Usage (from ``backend``)::

    DATABASE_URL='postgresql://...' python scripts/audit_champion_registration.py

The connection URL is read only from the environment.  PostgreSQL runs inside
an explicit READ ONLY transaction; SQLite enables ``PRAGMA query_only``.  The
script prints aggregate counts and the minimum tournament IDs needed to locate
problems.  It never prints user profile fields or authentication data.
"""

from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: E402


EMPTY_SLOT_CHARACTER_ID = 9999


def ids(values):
    return sorted(set(value for value in values if value is not None))


def add_issue(report, key, tournament_ids):
    affected = ids(tournament_ids)
    report[key] = {"count": len(affected), "tournament_ids": affected}


def team_characters(team):
    return (team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id)


def snapshot_audit(snapshot, players_by_id, deck_sets_by_player, teams_by_deck_set):
    raw_teams = Counter()
    raw_team_players = defaultdict(set)
    raw_chars = Counter()
    raw_char_players = defaultdict(set)
    tournament_players = [p for p in players_by_id.values() if p.tournament_id == snapshot.tournament_id]
    for player in tournament_players:
        for deck_set in deck_sets_by_player.get(player.id, []):
            for team in teams_by_deck_set.get(deck_set.id, []):
                character_ids = tuple(sorted(c for c in team_characters(team) if c is not None))
                if len(character_ids) == 5:
                    canonical = ",".join(map(str, character_ids))
                    raw_teams[canonical] += 1
                    raw_team_players[canonical].add(player.id)
                for character_id in set(character_ids):
                    if character_id == EMPTY_SLOT_CHARACTER_ID:
                        continue
                    raw_chars[character_id] += 1
                    raw_char_players[character_id].add(player.id)

    missing_player_count = any(
        "player_count" not in row
        for row in list(snapshot.team_usage or []) + list(snapshot.char_stats or [])
    )
    team_count_mismatches = 0
    team_player_mismatches = 0
    for row in snapshot.team_usage or []:
        canonical = row.get("canonical_id")
        team_count_mismatches += row.get("count") != raw_teams.get(canonical, 0)
        if "player_count" in row:
            team_player_mismatches += row.get("player_count") != len(raw_team_players.get(canonical, set()))
    char_count_mismatches = 0
    char_player_mismatches = 0
    for row in snapshot.char_stats or []:
        character_id = row.get("id")
        char_count_mismatches += row.get("count") != raw_chars.get(character_id, 0)
        if "player_count" in row:
            char_player_mismatches += row.get("player_count") != len(raw_char_players.get(character_id, set()))
    return {
        "missing_player_count": missing_player_count,
        "team_count_mismatches": team_count_mismatches,
        "team_player_count_mismatches": team_player_mismatches,
        "character_count_mismatches": char_count_mismatches,
        "character_player_count_mismatches": char_player_mismatches,
    }


def run(session):
    tournaments = session.query(models.Tournament).all()
    players = session.query(models.Player).all()
    deck_sets = session.query(models.DeckSet).all()
    teams = session.query(models.DeckTeam).all()
    matches = session.query(models.Match).all()
    rounds = session.query(models.RoundResult).all()
    snapshots = session.query(models.TournamentSnapshot).all()

    players_by_tournament = defaultdict(list)
    players_by_id = {}
    for player in players:
        players_by_tournament[player.tournament_id].append(player)
        players_by_id[player.id] = player
    deck_sets_by_player = defaultdict(list)
    for deck_set in deck_sets:
        deck_sets_by_player[deck_set.player_id].append(deck_set)
    teams_by_deck_set = defaultdict(list)
    for team in teams:
        teams_by_deck_set[team.deck_set_id].append(team)
    matches_by_tournament = defaultdict(list)
    for match in matches:
        matches_by_tournament[match.tournament_id].append(match)
    rounds_by_match = defaultdict(list)
    for round_result in rounds:
        rounds_by_match[round_result.match_id].append(round_result)

    report = {
        "tournaments_by_registration_scope": dict(Counter(t.registration_scope for t in tournaments)),
        "tournaments_by_publication_status": dict(Counter(t.publication_status for t in tournaments)),
        "player_count_distribution_by_scope": {},
    }
    for scope in ("full_64", "champion_8"):
        report["player_count_distribution_by_scope"][scope] = dict(sorted(Counter(
            len(players_by_tournament[t.id]) for t in tournaments if t.registration_scope == scope
        ).items()))

    champions = [t for t in tournaments if t.registration_scope == "champion_8"]
    add_issue(report, "champion_slot_missing", (
        t.id for t in champions
        if set(p.champion_slot for p in players_by_tournament[t.id] if p.champion_slot is not None) != set(range(1, 9))
    ))
    add_issue(report, "champion_slot_duplicate", (
        t.id for t in champions
        if any(count > 1 for count in Counter(p.champion_slot for p in players_by_tournament[t.id] if p.champion_slot is not None).values())
    ))
    add_issue(report, "champion_slot_out_of_range", (
        t.id for t in champions if any(p.champion_slot is not None and not 1 <= p.champion_slot <= 8 for p in players_by_tournament[t.id])
    ))
    add_issue(report, "champion_player_without_slot", (
        t.id for t in champions if any(p.champion_slot is None for p in players_by_tournament[t.id])
    ))
    add_issue(report, "seed_out_of_range", (
        t.id for t in tournaments if any(p.seed_number is not None and not 1 <= p.seed_number <= 64 for p in players_by_tournament[t.id])
    ))
    add_issue(report, "seed_duplicate", (
        t.id for t in tournaments if any(count > 1 for count in Counter(p.seed_number for p in players_by_tournament[t.id] if p.seed_number is not None).values())
    ))
    add_issue(report, "champion_seed_slot_mismatch", (
        t.id for t in champions if any(
            p.champion_slot in range(1, 9)
            and p.seed_number is not None
            and not ((p.champion_slot - 1) * 8 + 1 <= p.seed_number <= p.champion_slot * 8)
            for p in players_by_tournament[t.id]
        )
    ))

    duplicate_char_players = []
    duplicate_team_players = []
    deck_shape = Counter()
    for player in players:
        player_sets = deck_sets_by_player[player.id]
        player_teams = [team for deck_set in player_sets for team in teams_by_deck_set[deck_set.id]]
        deck_shape[(len(player_sets), len(player_teams))] += 1
        characters = [
            character_id
            for team in player_teams
            for character_id in team_characters(team)
            if character_id not in (None, EMPTY_SLOT_CHARACTER_ID)
        ]
        if len(characters) != len(set(characters)):
            duplicate_char_players.append(player.id)
        canonical_teams = [tuple(sorted(c for c in team_characters(team) if c is not None)) for team in player_teams]
        if len(canonical_teams) != len(set(canonical_teams)):
            duplicate_team_players.append(player.id)
    report["players_with_duplicate_character"] = len(duplicate_char_players)
    report["players_with_duplicate_five_character_team"] = len(duplicate_team_players)
    report["player_deckset_deckteam_distribution"] = {
        f"deck_sets={key[0]},deck_teams={key[1]}": value for key, value in sorted(deck_shape.items())
    }

    incomplete_published = []
    for tournament in champions:
        if tournament.publication_status != "published":
            continue
        tournament_players = players_by_tournament[tournament.id]
        team_count = sum(len(teams_by_deck_set[deck_set.id]) for p in tournament_players for deck_set in deck_sets_by_player[p.id])
        tournament_matches = matches_by_tournament[tournament.id]
        round_count = sum(len(rounds_by_match[match.id]) for match in tournament_matches)
        if (len(tournament_players), team_count, len(tournament_matches), round_count) != (8, 40, 7, 35):
            incomplete_published.append(tournament.id)
    add_issue(report, "published_champion_count_mismatch", incomplete_published)

    snapshot_results = {}
    fallback_ids = []
    for snapshot in snapshots:
        result = snapshot_audit(snapshot, players_by_id, deck_sets_by_player, teams_by_deck_set)
        snapshot_results[str(snapshot.tournament_id)] = result
        if result["missing_player_count"]:
            fallback_ids.append(snapshot.tournament_id)
    report["snapshot_comparison"] = snapshot_results
    report["legacy_snapshot_raw_fallback_tournament_ids"] = ids(fallback_ids)
    return report


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL must be set; no default database is used")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        if engine.dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION READ ONLY"))
        elif engine.dialect.name == "sqlite":
            session.execute(text("PRAGMA query_only = ON"))
        print(json.dumps(run(session), ensure_ascii=False, indent=2, sort_keys=True))
    finally:
        session.rollback()
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
