"""Read the public tournaments for one season and produce its Summary."""

from collections import Counter, defaultdict
from contextlib import nullcontext
from fractions import Fraction
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select

import models
from services import arena_phases, composition_analytics, cross_analytics, season_adoption
from services.team_statistics_display import canonical


PlayServer = Literal["JP", "GLOBAL", "KR", "NA", "SEA"]
STAGES = arena_phases.ANALYSIS_STAGES


def public_scope(db, championship_id, play_server):
    title = db.get(models.Championship, championship_id)
    if title is None:
        raise HTTPException(404, "Championship not found")

    rows = public_rows(db, championship_id, play_server)
    scope = {
        "championship_id": title.id,
        "title": title.name,
        "play_server": play_server,
        "tournament_ids": [row.id for row in rows],
        "tournament_count": len(rows),
        "full_64": sum(row.registration_scope == "full_64" for row in rows),
        "champion_8": sum(row.registration_scope == "champion_8" for row in rows),
    }
    return title, rows, scope


def public_rows(db, championship_id, play_server):
    tournament = models.Tournament
    return db.execute(select(
        tournament.id, tournament.registration_scope, tournament.deck_registration_phases.label("deck_registration_phases"),
    ).join(tournament.creator).where(
        tournament.championship_id == championship_id,
        tournament.publication_status == "published",
        tournament.has_match_data.is_(True),
        models.AppUser.play_server == play_server,
    ).order_by(tournament.id)).all()


EMPTY_NIKKE = 9999
MIN_SIDE_ROUNDS = 5
BATTLE_SIDES = ("attack", "defense")


def nikke_ids(team):
    return {cid for cid in (getattr(team, f"char{slot}_id") for slot in range(1, 6))
            if cid and cid != EMPTY_NIKKE}


def recorded_winners(match, sides):
    winners = defaultdict(set)
    for row in match.round_results:
        if 1 <= row.round_number <= 5:
            winners[row.round_number].add(row.winner_id)
    for number, recorded in winners.items():
        if len(recorded) == 1:
            winner = next(iter(recorded))
            if winner in sides:
                yield number, sides[winner]


def side_results(matches, legacy_decks):
    rounds_by_side, matches_by_side = Counter(), Counter()
    counts = {side: Counter() for side in BATTLE_SIDES}
    wins = {side: Counter() for side in BATTLE_SIDES}
    team_counts = {side: Counter() for side in BATTLE_SIDES}
    team_wins = {side: Counter() for side in BATTLE_SIDES}
    seen = set()
    for match in matches:
        match_key = (match.tournament_id, match.id)
        if match_key in seen:
            continue
        seen.add(match_key)
        if not match.attacker_id or not match.defender_id or match.attacker_id == match.defender_id:
            continue
        participants = dict(zip(BATTLE_SIDES, (match.attacker_id, match.defender_id)))
        sides = {player: side for side, player in participants.items()}
        if match.winner_id in sides:
            matches_by_side[sides[match.winner_id]] += 1
        decks = getattr(match, "arena_decks", legacy_decks)
        teams = {side: {team.team_number: team for team in decks[player].teams}
                 for side, player in participants.items() if decks.get(player)}
        for number, winner_side in recorded_winners(match, sides):
            rounds_by_side[winner_side] += 1
            for side, roster in teams.items():
                team = roster.get(number)
                if team is None:
                    continue
                characters = nikke_ids(team)
                counts[side].update(characters)
                if side == winner_side:
                    wins[side].update(characters)
                if len(characters) == 5 and min(characters) > 0:
                    key = canonical(team)
                    team_counts[side][key] += 1
                    team_wins[side][key] += int(side == winner_side)

    def totals(counter):
        return {"attack": counter["attack"], "defense": counter["defense"], "total": sum(counter.values())}

    return {"rounds": totals(rounds_by_side), "matches": totals(matches_by_side)}, counts, wins, team_counts, team_wins


def side_leaders(counts, wins):
    leaders = {}
    for side in BATTLE_SIDES:
        eligible = [(key, total) for key, total in counts[side].items() if total >= MIN_SIDE_ROUNDS]
        eligible.sort(key=lambda row: (-Fraction(wins[side][row[0]], row[1]), -row[1], row[0]))
        leaders[side] = [{
            "canonical_id": key, "character_ids": [int(cid) for cid in key.split(",")],
            "wins": wins[side][key], "losses": total - wins[side][key], "rounds": total,
            "win_rate": rate(wins[side][key], total),
        } for key, total in eligible[:5]]
    return {"minimum_rounds": MIN_SIDE_ROUNDS, **leaders}


def add_details_links(leaders, details_rows):
    by_key = {row["canonical_id"]: row for row in details_rows}
    for side in BATTLE_SIDES:
        for team in leaders[side]:
            row = by_key.get(team["canonical_id"])
            if not row:
                team["has_details"] = False
                continue
            wins, rounds = row["attack_wins"], row["attack_matches"]
            if side == "defense":
                wins, rounds = row["win_count"] - wins, row["total_matches"] - rounds
            team["has_details"] = (team["wins"], team["rounds"]) == (wins, rounds)

def rate(count, population):
    return round(count * 100 / population, 1) if population else None


def adoption(population, row=None):
    count = row["player_count"] if row else 0
    return {"count": count, "population": population, "rate": rate(count, population)}


def stage_ids(rows):
    return {stage: [row.id for row in rows if arena_phases.analysis_applicable(row, stage)]
            for stage in ("legacy", *STAGES)}


def stage_trends(db, groups, stages, trends, matches):
    return {stage: trends(groups[stage], db, stage, "all", shared_matches=matches)
            if groups[stage] else {"total_players": 0, "team_usage": []} for stage in stages}


def ranking_sections(groups, data):
    by_composition = {stage: {row["canonical_id"]: row for row in value["team_usage"]}
                      for stage, value in data.items()}
    result = {}
    for stage, stats in data.items():
        rows = stats["team_usage"]
        shortlist = []
        rank = 0
        previous = None
        for index, row in enumerate(rows):
            picked = row["player_count"]
            if picked != previous:
                previous = picked
                rank = index + 1
            if rank > 5:
                break
            key = row["canonical_id"]
            entry = {
                "rank": rank, "canonical_id": key, "character_ids": row["character_ids"],
                **adoption(stats["total_players"], row),
            }
            if stage == "final":
                entry["earlier"] = {
                    other: adoption(data[other]["total_players"], by_composition[other].get(key))
                    for other in ("league", "championship")
                }
            shortlist.append(entry)
        result[stage] = {
            "tournament_ids": groups[stage],
            "population": stats["total_players"],
            "teams": shortlist,
        }
    return result


def partner_counts(team_usage, debut_ids):
    result = {cid: Counter() for cid in debut_ids}
    for team in team_usage:
        members = set(team.get("character_ids") or ()) - {None, EMPTY_NIKKE}
        for cid in debut_ids & members:
            for partner in members - {cid}:
                result[cid][partner] += team["count"]
    return result


def character_section(count, population, wins, rounds, partners, registered_teams, names):
    leaders = sorted((cid for cid in partners if cid in names), key=lambda cid: (-partners[cid], cid))[:4]
    return {
        "count": count, "population": population, "rate": rate(count, population),
        "wins": wins, "losses": rounds - wins, "rounds": rounds, "win_rate": rate(wins, rounds),
        "partners": [{"id": cid, "name": names[cid], "rate": rate(partners[cid], registered_teams)}
                     for cid in leaders if registered_teams],
    }


def adoption_by_commander(db, bulk, ids, stage, debut_ids, population, adopted):
    if not ids:
        return
    wanted = set(ids)
    players = defaultdict(list)
    for player in bulk["players"]:
        if player.tournament_id in wanted:
            players[player.tournament_id].append(player.id)
    eligible = set()
    for tid in ids:
        if stage == "legacy":
            eligible.update(players[tid])
        else:
            eligible.update(arena_phases.analysis_qualified_ids(bulk["tournaments"][tid], db, stage, players[tid]))
    population.update(eligible)
    for deck in arena_phases.phase_deck_sets(db, eligible, stage):
        for team in deck.teams:
            for cid in debut_ids & nikke_ids(team):
                adopted[cid].add(deck.player_id)


def debut_statistics(db, character_ids, groups, stages, initial, aggregate, bulk, names, counts, wins):
    debut_ids = set(character_ids) & names.keys()
    if not debut_ids:
        return None
    data = {}
    beta_only = stages == ("legacy",)
    population = set()
    adopted = defaultdict(set)
    for stage in stages:
        ids = groups[stage]
        stats = aggregate(ids, db, stage) if ids else {}
        by_id = {(row.get("id") or row.get("character_id")): row for row in stats.get("character_stats", [])}
        partners = partner_counts(stats.get("team_usage", []), debut_ids)
        if not beta_only:
            adoption_by_commander(db, bulk, ids, stage, debut_ids, population, adopted)
        data[stage] = (stats.get("total_players", 0), by_id, partners)

    characters = []
    for cid in character_ids:
        if cid not in debut_ids:
            continue
        sections = {}
        overall_partners = Counter()
        registered_teams = 0
        for stage, (size, by_id, partners) in data.items():
            row = by_id.get(cid, {})
            appearances = row.get("count", 0)
            overall_partners.update(partners[cid])
            registered_teams += appearances
            sections[stage] = character_section(
                row.get("player_count", 0), size, row.get("win_count", 0), row.get("total_matches", 0),
                partners[cid], appearances, names,
            )
        sections["all"] = sections["legacy"] if beta_only else character_section(
            len(adopted[cid]), len(population), sum(wins[side][cid] for side in BATTLE_SIDES),
            sum(counts[side][cid] for side in BATTLE_SIDES), overall_partners, registered_teams, names,
        )
        current = {key: value for key, value in sections[initial].items() if key != "partners"}
        characters.append({"id": cid, "name": names[cid], **current, "sections": sections})
    return {
        "stage": initial, "tournament_ids": groups[initial], "characters": characters,
        "tournament_ids_by_stage": {stage: groups[stage] for stage in stages},
    }


def statistics(db, title, rows, scope, trends, aggregate):
    ids = scope["tournament_ids"]
    groups = stage_ids(rows)
    formal = any(row.deck_registration_phases for row in rows) if rows else bool(title.deck_registration_phases)
    stages = [*STAGES, "legacy"] if formal and groups["legacy"] else STAGES if formal else ("legacy",)
    initial = "final" if formal else "legacy"
    character_stage = "championship" if formal else "legacy"
    debut_ids = title.debut_character_ids or []
    cache_kind = repr(("season-summary-v5", title.id, scope["play_server"], debut_ids))

    def compute():
        with (arena_phases.analysis_scope(db, ids) if ids else nullcontext({})) as bulk:
            matches = arena_phases.effective_matches(db, ids) if ids else []
            legacy_decks = {}
            for deck in bulk.get("decks", []):
                legacy_decks.setdefault(deck.player_id, deck)
            sides, counts, wins, team_counts, team_wins = side_results(matches, legacy_decks)
            leaders = side_leaders(team_counts, team_wins)
            if any(leaders[side] for side in BATTLE_SIDES):
                # Some recorded teams have no Details card, and malformed rounds can differ.
                # Verify the actual Details totals once over the shared analysis scope.
                details = composition_analytics.build(db, bulk, ids, None, matches=matches)
                add_details_links(leaders, details["teams"]["all"])
            catalog = {row.id: row for row in db.execute(select(
                models.Character.id, models.Character.name, models.Character.weapon, models.Character.burst_phase,
            ))} if ids or debut_ids else {}
            names = {cid: row.name for cid, row in catalog.items()}
            stage_data = stage_trends(db, groups, stages, trends, matches)
            return {
                **sides,
                "side_leaders": leaders,
                "initial_stage": initial,
                "rankings": ranking_sections(groups, stage_data),
                "weapon_adoption": season_adoption.weapon_statistics(db, bulk, groups, stages, catalog),
                "burst_rankings": {stage: season_adoption.burst_rankings(stats, catalog)
                                   for stage, stats in stage_data.items()},
                "debut": debut_statistics(db, debut_ids, groups, stages, character_stage, aggregate, bulk, names, counts, wins),
            }

    return {**scope, **cross_analytics.cached(db, ids, "all", cache_kind, compute)}
