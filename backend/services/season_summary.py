"""Read the public tournaments for one season and produce its Summary."""

from collections import Counter, defaultdict
from contextlib import nullcontext
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select

import models
from services import arena_phases, cross_analytics


PlayServer = Literal["JP", "GLOBAL", "KR", "NA", "SEA"]
STAGES = arena_phases.ANALYSIS_STAGES


def public_scope(db, championship_id, play_server):
    title = db.get(models.Championship, championship_id)
    if title is None:
        raise HTTPException(404, "Championship not found")

    tournament = models.Tournament
    rows = db.execute(select(
        tournament.id, tournament.registration_scope, tournament.deck_registration_phases.label("deck_registration_phases"),
    ).join(tournament.creator).where(
        tournament.championship_id == championship_id,
        tournament.publication_status == "published",
        tournament.has_match_data.is_(True),
        models.AppUser.play_server == play_server,
    ).order_by(tournament.id)).all()
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


def side_results(matches):
    rounds_by_side, matches_by_side = Counter(), Counter()
    seen = set()
    for match in matches:
        match_key = (match.tournament_id, match.id)
        if match_key in seen:
            continue
        seen.add(match_key)
        attacking, defending = match.attacker_id, match.defender_id
        if not attacking or not defending or attacking == defending:
            continue
        side = {attacking: "attack", defending: "defense"}
        if match.winner_id in side:
            matches_by_side[side[match.winner_id]] += 1
        winners = defaultdict(set)
        for row in match.round_results:
            if 1 <= row.round_number <= 5:
                winners[row.round_number].add(row.winner_id)
        for recorded in winners.values():
            if len(recorded) == 1:
                winner = next(iter(recorded))
                if winner in side:
                    rounds_by_side[side[winner]] += 1

    def totals(counts):
        return {"attack": counts["attack"], "defense": counts["defense"], "total": sum(counts.values())}

    return {"rounds": totals(rounds_by_side), "matches": totals(matches_by_side)}


def rate(count, population):
    return round(count * 100 / population, 1) if population else None


def adoption(population, row=None):
    count = row["player_count"] if row else 0
    return {"count": count, "population": population, "rate": rate(count, population)}


def stage_ids(rows):
    return {stage: [row.id for row in rows if arena_phases.analysis_applicable(row, stage)]
            for stage in ("legacy", *STAGES)}


def ranking_sections(db, groups, stages, trends, matches):
    data = {stage: trends(groups[stage], db, stage, "all", shared_matches=matches)
            if groups[stage] else {"total_players": 0, "team_usage": []} for stage in stages}
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


def debut_statistics(db, character_ids, groups, stage, aggregate):
    if not character_ids:
        return None
    by_id = {row.id: row.name for row in db.execute(select(models.Character.id, models.Character.name)
             .where(models.Character.id.in_(character_ids)))}
    if not by_id:
        return None
    ids = groups[stage]
    stats = aggregate(ids, db, stage) if ids else {}
    chars = {(row.get("id") or row.get("character_id")): row for row in stats.get("character_stats", [])}
    population = stats.get("total_players", 0)
    values = []
    for cid in character_ids:
        if cid not in by_id:
            continue
        row = chars.get(cid, {})
        total = row.get("total_matches", 0)
        wins = row.get("win_count", 0)
        values.append({
            "id": cid, "name": by_id[cid], **adoption(population, row),
            "wins": wins, "losses": total - wins, "rounds": total,
            "win_rate": row.get("win_rate") if total else None,
        })
    return {"stage": stage, "tournament_ids": ids, "characters": values}


def statistics(db, title, rows, scope, trends, aggregate):
    ids = scope["tournament_ids"]
    groups = stage_ids(rows)
    formal = any(row.deck_registration_phases for row in rows) if rows else bool(title.deck_registration_phases)
    stages = [*STAGES, "legacy"] if formal and groups["legacy"] else STAGES if formal else ("legacy",)
    initial = "final" if formal else "legacy"
    character_stage = "championship" if formal else "legacy"
    debut_ids = title.debut_character_ids or []
    # Include the selection in the key so a warmed response cannot serve a
    # previous roster after an administrator edits this title.
    cache_kind = f"season-summary-v1:{title.id}:{scope['play_server']}:{','.join(map(str, debut_ids))}"

    def compute():
        with arena_phases.analysis_scope(db, ids) if ids else nullcontext():
            matches = arena_phases.effective_matches(db, ids) if ids else []
            return {
                **side_results(matches),
                "initial_stage": initial,
                "rankings": ranking_sections(db, groups, stages, trends, matches),
                "debut": debut_statistics(db, debut_ids, groups, character_stage, aggregate),
            }

    return {**scope, **cross_analytics.cached(db, ids, "all", cache_kind, compute)}
