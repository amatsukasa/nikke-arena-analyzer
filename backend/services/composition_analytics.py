"""Canonical composition cards and their recorded round history."""
from collections import Counter, defaultdict

import models
from services import arena_phases, cross_analytics, team_statistics_display as display
from services.tournament_results import calculate_player_results, result_label

STAGES = ("legacy", *arena_phases.ANALYSIS_STAGES)


def load(db, tournament_ids, seed):
    def compute():
        with arena_phases.analysis_scope(db, tournament_ids) as scope:
            return build(db, scope, tournament_ids, seed)
    return cross_analytics.cached(db, tournament_ids, "all", f"compositions-v1:{seed}", compute)


def build(db, scope, tournament_ids, seed):
    tournaments = {tid: scope["tournaments"][tid] for tid in tournament_ids if tid in scope["tournaments"]}
    scope_players = [p for p in scope["players"] if p.tournament_id in tournaments]
    players = {p.id: p for p in scope_players if seed is None or p.seed_number == seed}
    matches = arena_phases.effective_matches(db, tournaments)
    players_by_tournament, matches_by_tournament = defaultdict(list), defaultdict(list)
    for player in scope_players:
        players_by_tournament[player.tournament_id].append(player)
    for match in matches:
        matches_by_tournament[match.tournament_id].append(match)
    results = {}
    for tid, tournament in tournaments.items():
        results.update({pid: result_label(code) for pid, code in calculate_player_results(
            tournament, players_by_tournament[tid], matches_by_tournament[tid]).items()})

    legacy_decks = {}
    for deck in scope["decks"]:
        legacy_decks.setdefault(deck.player_id, deck)
    matches_by_stage = defaultdict(list)
    for match in matches:
        phase = arena_phases.normalized_stage(tournaments[match.tournament_id], getattr(match, "arena_phase", "initial"))
        if phase in STAGES:
            matches_by_stage[phase].append(match)
    character_ids = set()
    sections, history, played_only = {}, {}, {}
    populations = {}
    for phase in STAGES:
        applicable = {p.id for p in players.values() if arena_phases.analysis_applicable(tournaments[p.tournament_id], phase)}
        populations[phase] = {pid for tid, tournament in tournaments.items() if arena_phases.analysis_applicable(tournament, phase)
                              for pid in arena_phases.analysis_qualified_ids(
                                  tournament, db, phase, [p.id for p in players_by_tournament[tid]]) if pid in applicable}
        if phase == "legacy":
            decks = [deck for pid, deck in legacy_decks.items() if pid in applicable]
        else:
            decks = arena_phases.phase_deck_sets(db, applicable, phase) if applicable else []
        rows = {}
        stage_matches = matches_by_stage[phase]
        metadata = display.metadata(decks, stage_matches, results, phase, tournaments, players.values())
        for deck in decks:
            player = players[deck.player_id]
            for team in sorted(deck.teams, key=lambda value: value.team_number):
                key = display.canonical(team)
                if key is None:
                    continue
                ids = [getattr(team, f"char{i}_id") for i in range(1, 6)]
                character_ids.update(ids)
                row = rows.setdefault(key, new_row(phase, key, ids))
                identity = f"{player.tournament_id}:{player.id}"
                row["registrations"] += 1
                row["adopters"][identity] = {
                    "player_name": player.name, "tournament_name": tournaments[player.tournament_id].name,
                    "tournament_id": player.tournament_id, "result": results.get(player.id),
                }
                position(row, team.team_number)["adopters"].add(identity)
        played_only[phase] = {}
        history[phase] = record_rounds(rows, played_only[phase], stage_matches, legacy_decks, players, phase)
        for key, row in rows.items():
            info = metadata[key]
            row.update({field: info[field] for field in (
                "composition_best_result", "composition_result_ceiling", "commander_best_result",
                "usage_history", "usage_history_status",
            )})
            for number, item in row["position_stats"].items():
                item["composition_best_result"] = info["position_composition_results"].get(str(number))
        sections[phase] = rows

    catalog = {c.id: {"id": c.id, "name": c.name, "rarity": c.rarity}
               for c in db.query(models.Character).filter(models.Character.id.in_(character_ids))} if character_ids else {}
    all_rows = defaultdict(list)
    for rows in sections.values():
        for key, row in rows.items():
            all_rows[key].append(row)
    # Superseded registrations contribute their effective recorded rounds across stages.
    for rows in played_only.values():
        for key in rows.keys() & all_rows.keys():
            all_rows[key].append(rows[key])
    overall_population = len(set().union(*populations.values()))
    overall = [finish(rows, "all", catalog, overall_population) for rows in all_rows.values()]
    usage = Counter()
    for row in overall:
        for cid in set(row["character_ids"]):
            usage[cid] += row["registration_count"]
    return {
        "teams": {**{phase: [finish([row], phase, catalog, len(populations[phase])) for row in rows.values()]
                      for phase, rows in sections.items()},
                  "all": overall},
        "matchups": history,
        "character_usage": [{"id": cid, "count": count} for cid, count in sorted(usage.items())],
    }


def position(row, number):
    return row["position_stats"].setdefault(number, {"adopters": set(), "wins": 0, "total": 0})


def new_row(phase, key, ids=()):
    return {
        "canonical_id": key, "character_ids": ids, "registrations": 0, "adopters": {},
        "win_count": 0, "total_matches": 0, "attack_wins": 0, "attack_matches": 0,
        "position_stats": {}, "phase": phase, "composition_best_result": None,
        "composition_result_ceiling": max(display.RESULT_ORDER.values()),
        "commander_best_result": None, "usage_history": [], "usage_history_status": "verified",
    }


def record_rounds(rows, played_only, matches, legacy_decks, players, phase):
    history = []
    for match in matches:
        participants = (match.attacker_id, match.defender_id)
        if not any(pid in players for pid in participants):
            continue
        decks = getattr(match, "arena_decks", legacy_decks)
        teams = [{t.team_number: t for t in decks[pid].teams} if pid in decks else {} for pid in participants]
        for rr in match.round_results:
            if rr.winner_id not in participants:
                continue
            side_teams = [side.get(rr.round_number) for side in teams]
            keys = [display.canonical(team) if team is not None else None for team in side_teams]
            for side, (pid, key) in enumerate(zip(participants, keys)):
                if pid in players and key is not None:
                    row = rows.get(key)
                    if row is None:
                        row = played_only.setdefault(key, new_row(phase, key))
                    win = int(rr.winner_id == pid)
                    row["win_count"] += win
                    row["total_matches"] += 1
                    if side == 0:
                        row["attack_wins"] += win
                        row["attack_matches"] += 1
                    item = position(row, rr.round_number)
                    item["wins"] += win
                    item["total"] += 1
            if all(keys):
                a, d = side_teams
                history.append({
                    "match_id": match.id, "round_number": rr.round_number, "stage": match.stage,
                    "registration_phase": phase, "tournament_id": match.tournament_id,
                    "tournament_name": match.tournament.name, "attacker_name": match.attacker.name,
                    "defender_name": match.defender.name, "winner_is_attacker": rr.winner_id == participants[0],
                    "attacker_player_id": participants[0], "defender_player_id": participants[1],
                    "attacker_team_id": a.id, "defender_team_id": d.id,
                    "attacker_team_number": a.team_number, "defender_team_number": d.team_number,
                    "canonical_attacker": keys[0], "canonical_defender": keys[1],
                    "attacker_team": [getattr(a, f"char{i}_id") for i in range(1, 6)],
                    "defender_team": [getattr(d, f"char{i}_id") for i in range(1, 6)],
                    "attacker_collections": [getattr(a, f"collection{i}") for i in range(1, 6)],
                    "defender_collections": [getattr(d, f"collection{i}") for i in range(1, 6)],
                    "bracket_stage": getattr(match, "bracket_stage", None),
                    "bracket_slot": getattr(match, "bracket_slot", None),
                })
    return history


def rate(wins, rounds):
    return round(wins / rounds * 100, 1) if rounds else None


def finish(rows, phase, catalog, population):
    first = rows[0]
    wins = sum(row["win_count"] for row in rows)
    rounds = sum(row["total_matches"] for row in rows)
    adopters = {key: adopter for row in rows for key, adopter in row["adopters"].items()}
    best = display.highest(row["composition_best_result"] for row in rows)
    if best and any(row["composition_result_ceiling"] < display.RESULT_ORDER[best] for row in rows):
        best = None
    positions = []
    for number in range(1, 6):
        entries = [row["position_stats"][number] for row in rows if number in row["position_stats"]]
        position_adopters = {pid for entry in entries for pid in entry["adopters"]}
        count = len(position_adopters)
        position_wins = sum(entry["wins"] for entry in entries)
        position_rounds = sum(entry["total"] for entry in entries)
        values = [entry.get("composition_best_result") for entry in entries if entry["adopters"]]
        positions.append({"position": number, "count": count, "pct": round(count / len(adopters) * 100, 1),
                          "wins": position_wins, "total": position_rounds,
                          "win_rate": rate(position_wins, position_rounds),
                          "composition_best_result": display.highest(values) if values and all(values) else None,
                          "commander_results": display.finish_counts(position_adopters,
                              {pid: adopters[pid]["result"] for pid in position_adopters if adopters[pid]["result"]})})
    history = Counter()
    for row in rows:
        history.update({item["stage"]: item["round_count"] for item in row["usage_history"]})
    commander_best = display.highest(row["commander_best_result"] for row in rows)
    attack_wins = sum(row["attack_wins"] for row in rows)
    attack_matches = sum(row["attack_matches"] for row in rows)
    return {
        "canonical_id": first["canonical_id"], "character_ids": first["character_ids"],
        "characters": [catalog[cid] for cid in first["character_ids"] if cid in catalog],
        "registration_phase": phase, "registration_phases": [row["phase"] for row in rows if row["registrations"]],
        "count": len(adopters), "player_count": len(adopters),
        "adoption_rate": rate(len(adopters), population) or 0.0,
        "registration_count": sum(row["registrations"] for row in rows),
        "win_count": wins, "total_matches": rounds, "win_rate": rate(wins, rounds),
        "attack_wins": attack_wins, "attack_matches": attack_matches,
        "composition_best_result": best, "composition_result_status": "known" if best else "undetermined",
        "commander_best_result": commander_best,
        "best_result": next((label for label, code in display.RESULT_CODES.items() if code == commander_best), commander_best),
        "commander_results": display.finish_counts(adopters, {key: a["result"] for key, a in adopters.items() if a["result"]}),
        "adopted_players": list(adopters.values()), "position_stats": positions,
        "usage_history": [{"stage": stage, "round_count": count} for stage, count in sorted(history.items())],
        "usage_history_status": ("legacy_unverifiable" if any(row["usage_history_status"] == "legacy_unverifiable"
                                                              for row in rows) else "verified"),
    }


def details(data, teams, phase, requested):
    choices = [{field: row[field] for field in ("canonical_id", "character_ids", "registration_phases")}
               for row in data["teams"]["all"]]
    default_team = max(teams or data["teams"]["all"], key=lambda row: row["count"], default=None)
    selected = requested or (default_team["canonical_id"] if default_team else "")
    team = next((row for row in teams if row["canonical_id"] == selected), None)
    phases = STAGES if phase == "all" else (phase,)
    matchups = [row for stage in phases for row in data["matchups"].get(stage, [])
                if selected in (row["canonical_attacker"], row["canonical_defender"])]
    return {"canonical_id": selected, "team": team, "choices": choices, "matchups": matchups}
