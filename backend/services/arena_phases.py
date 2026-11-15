"""Append-only official-arena registration, progression and phase-separated statistics.

Legacy tables are read only here. No migration/backfill of season-one data is required.
Every write is serialized on the tournament row, including eligibility rechecks.
"""
from collections import Counter
from hashlib import sha256
import json

from fastapi import HTTPException
import models
from services.collection_classifier import COLLECTION_VALUES

PHASES = ("initial", "best8", "final")


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def supported(tournament):
    return bool(tournament.deck_registration_phases)


def legacy_teams(player, db):
    decks = db.query(models.DeckSet).filter(models.DeckSet.player_id == player.id).order_by(models.DeckSet.id).all()
    # Ambiguous legacy sets must never silently become a complete registration.
    if len(decks) != 1:
        return []
    return [{"team_number": t.team_number, "characters": [
        {"id": getattr(t, f"char{i}_id"), "collection_level": getattr(t, f"collection{i}")}
        for i in range(1, 6)]} for t in sorted(decks[0].teams, key=lambda t: t.team_number)]


def complete(teams):
    if len(teams) != 5 or sorted(t.get("team_number", 0) if type(t.get("team_number")) is int else 0 for t in teams) != [1, 2, 3, 4, 5]:
        return False
    ids = []
    for t in teams:
        chars = t.get("characters", [])
        if len(chars) != 5 or any(type(c.get("id")) is not int or c["id"] <= 0 for c in chars):
            return False
        ids.extend(c["id"] for c in chars if c["id"] != 9999)
    return len(ids) == len(set(ids))


def definitions(tournament):
    size = 8 if tournament.registration_scope == "champion_8" else 64
    rounds = [8, 4, 2] if size == 8 else [64, 32, 16, 8, 4, 2]
    result = []
    previous = None
    for remaining in rounds:
        for slot in range(1, remaining // 2 + 1):
            phase = "final" if remaining == 2 else "best8" if size == 64 and remaining <= 8 else "initial"
            result.append({"key": f"{remaining}:{slot}", "remaining": remaining, "slot": slot,
                "phase": phase, "sources": [f"{previous}:{slot * 2 - 1}", f"{previous}:{slot * 2}"] if previous else []})
        previous = remaining
    return result


def context(tournament, db):
    players = db.query(models.Player).filter(models.Player.tournament_id == tournament.id).all()
    by_position = {(p.champion_slot if tournament.registration_scope == "champion_8" else p.seed_number): p.id for p in players}
    legacy = db.query(models.Match).filter(models.Match.tournament_id == tournament.id).order_by(models.Match.id).all()
    revisions = db.query(models.ArenaMatchRevision).filter(models.ArenaMatchRevision.tournament_id == tournament.id).order_by(models.ArenaMatchRevision.id).all()
    latest = {r.match_key: r for r in revisions}
    registrations = db.query(models.ArenaDeckRegistration).filter(models.ArenaDeckRegistration.tournament_id == tournament.id).order_by(models.ArenaDeckRegistration.id).all()
    latest_registration = {(r.player_id, r.phase): r for r in registrations}
    legacy_by_player = {p.id: legacy_teams(p, db) for p in players}
    nodes = {}
    qualifications = {(p.id, "initial"): "initial" for p in players}

    def registration(pid, phase):
        qualification = qualifications.get((pid, phase))
        revision = latest_registration.get((pid, phase))
        if qualification and revision and revision.qualification == qualification:
            return revision.teams, revision.id
        if phase == "initial" and revision is None:
            return legacy_by_player.get(pid, []), None
        return [], None

    for definition in definitions(tournament):
        sources = definition["sources"]
        if sources:
            source_nodes = [nodes[k] for k in sources]
            participants = [n["winner_id"] for n in source_nodes]
            upstream = fingerprint([n["advancement"] for n in source_nodes])
        else:
            participants = [by_position.get(definition["slot"] * 2 - 1), by_position.get(definition["slot"] * 2)]
            upstream = fingerprint(participants)
        phase = definition["phase"]
        for pid in participants:
            if pid and phase != "initial":
                # A phase spans multiple rounds: qualification is established only at its first round.
                if definition["remaining"] == (8 if phase == "best8" else 2):
                    source = next((nodes[k] for k in sources if nodes[k]["winner_id"] == pid), None)
                    qualifications[(pid, phase)] = fingerprint([phase, source["advancement"] if source else pid])
        teams = [registration(pid, phase) if pid else ([], None) for pid in participants]
        stored = latest.get(definition["key"])
        active = None
        legacy_match = None
        if stored and stored.upstream == upstream and [stored.attacker_id, stored.defender_id] == participants:
            active = stored
        elif stored is None and all(participants) and all(nodes[k]["legacy_lineage"] for k in sources):
            # Existing results always retain the original initial decks, even for an old final.
            for match in legacy:
                correct_stage = ((match.bracket_stage == {8: "quarterfinal", 4: "semifinal", 2: "final"}.get(definition["remaining"]) and match.bracket_slot == definition["slot"])
                    if tournament.registration_scope == "champion_8" else
                    True)
                if correct_stage and {match.attacker_id, match.defender_id} == set(participants) and match.winner_id in participants and sorted(r.round_number for r in match.round_results) == [1, 2, 3, 4, 5] and all(r.winner_id in participants for r in match.round_results) and match.winner_id == (match.attacker_id if sum(r.winner_id == match.attacker_id for r in match.round_results) >= 3 else match.defender_id):
                    legacy_match = match
        winner_id = active.winner_id if active else legacy_match.winner_id if legacy_match else None
        ready = all(participants) and participants[0] != participants[1] and all(complete(t[0]) for t in teams)
        node = {**definition, "participants": participants, "upstream": upstream,
            "winner_id": winner_id, "can_register": bool(ready), "status": "complete" if winner_id else "ready" if ready else "locked",
            "teams": [t[0] for t in teams], "registration_ids": [t[1] for t in teams],
            "revision_id": active.id if active else None, "legacy_match_id": legacy_match.id if legacy_match else None,
            "result_phase": active.phase if active else "initial" if legacy_match else phase,
            "rounds": active.rounds if active else [r.winner_id for r in sorted(legacy_match.round_results, key=lambda r: r.round_number)] if legacy_match else [],
            "result_teams": [active.attacker_teams, active.defender_teams] if active else [legacy_by_player.get(legacy_match.attacker_id, []), legacy_by_player.get(legacy_match.defender_id, [])] if legacy_match else [],
            "result_participants": [active.attacker_id, active.defender_id] if active else [legacy_match.attacker_id, legacy_match.defender_id] if legacy_match else [],
            "legacy_lineage": stored is None and all(nodes[k]["legacy_lineage"] for k in sources),
            "advancement": fingerprint([definition["key"], active.id if active else f"legacy:{legacy_match.id}" if legacy_match else None, winner_id])}
        nodes[definition["key"]] = node
    return players, nodes, qualifications, registration


def phase_statistics(phase, nodes, player_decks):
    adoption = Counter()
    team_adoption, team_wins, team_played = Counter(), Counter(), Counter()
    for teams in player_decks:
        if complete(teams):
            team_adoption.update(set(tuple(sorted(c["id"] for c in team["characters"])) for team in teams))
            for team in teams:
                adoption.update(c["id"] for c in team["characters"] if c["id"] != 9999)
    wins, played = Counter(), Counter()
    matches = 0
    for node in nodes.values():
        if not node["winner_id"] or node["result_phase"] != phase:
            continue
        matches += 1
        for pid, teams in zip(node["result_participants"], node["result_teams"]):
            for team in teams:
                rn = team["team_number"] - 1
                if rn not in range(len(node["rounds"])):
                    continue
                canonical = tuple(sorted(c["id"] for c in team["characters"] if c["id"] is not None))
                if len(canonical) == 5:
                    team_played[canonical] += 1
                    team_wins[canonical] += node["rounds"][rn] == pid
                for c in team["characters"]:
                    cid = c["id"]
                    if cid and cid != 9999:
                        played[cid] += 1
                        wins[cid] += node["rounds"][rn] == pid
    return {"matches": matches, "registered_players": sum(complete(t) for t in player_decks),
        "teams": [{"character_ids": list(key), "adoptions": team_adoption[key], "wins": team_wins[key], "played": team_played[key]} for key in sorted(set(team_adoption) | set(team_played))],
        "characters": [{"id": cid, "adoptions": adoption[cid], "wins": wins[cid], "played": played[cid]} for cid in sorted(set(adoption) | set(played))]}


def state(tournament, db):
    players, nodes, qualifications, registration = context(tournament, db)
    phases = ["initial", "final"] if tournament.registration_scope == "champion_8" else list(PHASES)
    deck_entries = []
    for player in players:
        for phase in phases:
            teams, revision_id = registration(player.id, phase)
            deck_entries.append({"player_id": player.id, "phase": phase, "eligible": (player.id, phase) in qualifications,
                "qualification": qualifications.get((player.id, phase)), "teams": teams, "revision_id": revision_id, "complete": complete(teams)})
    return {"format": tournament.registration_scope, "phases": phases,
        "players": [{"id": p.id, "name": p.name, "seed_number": p.seed_number, "champion_slot": p.champion_slot, "icon_url": p.icon_url} for p in players],
        "registrations": deck_entries, "matches": list(nodes.values()),
        "statistics": {phase: phase_statistics(phase, nodes, [e["teams"] for e in deck_entries if e["phase"] == phase and e["eligible"]]) for phase in phases}}


def validate_teams(teams, db):
    if not isinstance(teams, list) or len(teams) != 5:
        raise HTTPException(422, "Exactly five teams are required")
    cleaned = []
    for team in teams:
        if not isinstance(team, dict) or type(team.get("team_number")) is not int or not isinstance(team.get("characters"), list) or len(team["characters"]) != 5 or any(not isinstance(c, dict) for c in team["characters"]):
            raise HTTPException(422, "Invalid team")
        cleaned.append({"team_number": team.get("team_number"), "characters": [
            {"id": c.get("id"), "collection_level": c.get("collection_level") if c.get("collection_level") in COLLECTION_VALUES else None}
            for c in team["characters"] if isinstance(c, dict)]})
    if not complete(cleaned):
        raise HTTPException(422, "Five resolved teams with no duplicate characters are required")
    ids = {c["id"] for t in cleaned for c in t["characters"] if c["id"] != 9999}
    known = {c.id for c in db.query(models.Character).filter(models.Character.id.in_(ids)).all()}
    if ids != known:
        raise HTTPException(422, "Unknown character")
    return sorted(cleaned, key=lambda t: t["team_number"])


def save_registration(tournament, player_id, phase, payload, db):
    _, _, qualifications, _ = context(tournament, db)
    qualification = qualifications.get((player_id, phase))
    if qualification is None:
        raise HTTPException(409, "Player is not qualified for this registration phase")
    if payload.get("qualification") != qualification:
        raise HTTPException(409, "Qualification changed; reload before saving")
    latest = db.query(models.ArenaDeckRegistration).filter_by(tournament_id=tournament.id, player_id=player_id, phase=phase).order_by(models.ArenaDeckRegistration.id.desc()).first()
    if payload.get("revision_id") != (latest.id if latest and latest.qualification == qualification else None):
        raise HTTPException(409, "Registration changed; reload before saving")
    teams = validate_teams(payload.get("teams"), db)
    db.add(models.ArenaDeckRegistration(tournament_id=tournament.id, player_id=player_id, phase=phase, qualification=qualification, teams=teams))
    db.commit()
    return state(tournament, db)


def save_result(tournament, key, payload, db):
    _, nodes, _, _ = context(tournament, db)
    node = nodes.get(key)
    if not node or node["status"] == "locked":
        raise HTTPException(409, "Qualified participants and five complete teams are required")
    if not all(complete(t) for t in node["teams"]):
        raise HTTPException(409, "Complete phase registrations are required")
    if payload.get("upstream") != node["upstream"] or payload.get("registration_ids") != node["registration_ids"] or payload.get("revision_id") != node["revision_id"]:
        raise HTTPException(409, "Match or registration changed; reload before saving")
    participants = node["participants"]
    rounds = payload.get("rounds")
    if not isinstance(rounds, list) or len(rounds) != 5 or any(type(pid) is not int or pid not in participants for pid in rounds):
        raise HTTPException(422, "Exactly five participant round winners are required")
    winner = participants[0] if rounds.count(participants[0]) >= 3 else participants[1]
    db.add(models.ArenaMatchRevision(tournament_id=tournament.id, match_key=key, phase=node["phase"], upstream=node["upstream"],
        attacker_id=participants[0], defender_id=participants[1], winner_id=winner,
        attacker_registration_id=node["registration_ids"][0], defender_registration_id=node["registration_ids"][1],
        attacker_teams=node["teams"][0], defender_teams=node["teams"][1], rounds=rounds))
    db.commit()
    return state(tournament, db)


def history(tournament, db):
    players = db.query(models.Player).filter_by(tournament_id=tournament.id).all()
    originals = {p.id: legacy_teams(p, db) for p in players}
    registrations = [{"id": r.id, "player_id": r.player_id, "phase": r.phase, "teams": r.teams}
        for r in db.query(models.ArenaDeckRegistration).filter_by(tournament_id=tournament.id).order_by(models.ArenaDeckRegistration.id.desc()).all()]
    for deck in db.query(models.DeckSet).filter(models.DeckSet.player_id.in_(list(originals))).all():
        registrations.append({"id": -deck.id, "player_id": deck.player_id, "phase": "initial", "teams": [
            {"team_number": t.team_number, "characters": [{"id": getattr(t, f"char{i}_id"), "collection_level": getattr(t, f"collection{i}")} for i in range(1, 6)]}
            for t in sorted(deck.teams, key=lambda t: t.team_number)]})
    results = [{"id": r.id, "key": r.match_key, "phase": r.phase, "participants": [r.attacker_id, r.defender_id],
        "winner_id": r.winner_id, "rounds": r.rounds, "teams": [r.attacker_teams, r.defender_teams]}
        for r in db.query(models.ArenaMatchRevision).filter_by(tournament_id=tournament.id).order_by(models.ArenaMatchRevision.id.desc()).all()]
    for match in db.query(models.Match).filter_by(tournament_id=tournament.id).all():
        results.append({"id": -match.id, "key": match.stage, "phase": "initial", "participants": [match.attacker_id, match.defender_id],
            "winner_id": match.winner_id, "rounds": [r.winner_id for r in sorted(match.round_results, key=lambda r: r.round_number)],
            "teams": [originals.get(match.attacker_id, []), originals.get(match.defender_id, [])]})
    return {"registrations": registrations, "results": results}


def publication_readiness(tournament, db):
    data = state(tournament, db)
    initial = [r for r in data["registrations"] if r["phase"] == "initial"]
    count = len(data["players"])
    complete_count = sum(r["complete"] for r in initial)
    match_count = sum(n["status"] == "complete" for n in data["matches"])
    issues = []
    if not count or complete_count != count:
        issues.append({"code": "incomplete_initial", "message": "Every player needs five complete initial teams"})
    if tournament.registration_scope == "champion_8" and (count != 8 or match_count != 7):
        issues.append({"code": "incomplete_bracket", "message": "Eight players and seven complete matches are required"})
    return {"can_publish": not issues, "errors": issues, "warnings": [], "player_count": count,
        "complete_player_count": complete_count, "incomplete_player_count": count-complete_count,
        "unresolved_slot_count": sum(25 for r in initial if not r["complete"]), "match_count": match_count,
        "invalid_slots": [], "invalid_match_slots": [],
        "counts": {"players": count, "complete_players": complete_count, "teams": complete_count * 5, "matches": match_count, "round_results": match_count * 5}}


# Read adapters keep existing initial-registration analytics separate from later phases.
# These are transient objects: they are never attached to the Session or persisted.
def projected_deck(player_id, teams, identity):
    from types import SimpleNamespace
    rows = []
    for team in teams:
        fields = {"team_number": team["team_number"], "deck_set_id": identity}
        for index, c in enumerate(team["characters"], 1):
            fields[f"char{index}_id"] = c["id"]
            fields[f"collection{index}"] = c.get("collection_level")
        rows.append(SimpleNamespace(**fields))
    return SimpleNamespace(id=identity, player_id=player_id, teams=rows, created_at=0)


def initial_deck_sets(db, player_ids):
    players = db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()
    tids = {p.tournament_id for p in players}
    arenas = {t.id: t for t in db.query(models.Tournament).filter(models.Tournament.id.in_(tids)).all() if supported(t)}
    regular_ids = [p.id for p in players if p.tournament_id not in arenas]
    result = db.query(models.DeckSet).filter(models.DeckSet.player_id.in_(regular_ids)).all() if regular_ids else []
    for tournament in arenas.values():
        revisions = db.query(models.ArenaDeckRegistration).filter_by(tournament_id=tournament.id, phase="initial").order_by(models.ArenaDeckRegistration.id).all()
        latest = {r.player_id: r for r in revisions}
        for player in players:
            if player.tournament_id != tournament.id:
                continue
            revision = latest.get(player.id)
            teams = revision.teams if revision else legacy_teams(player, db)
            if teams:
                result.append(projected_deck(player.id, teams, -player.id))
    return result


def effective_matches(db, tournament_ids):
    from types import SimpleNamespace
    tournaments = db.query(models.Tournament).filter(models.Tournament.id.in_(tournament_ids)).all()
    result = []
    for tournament in tournaments:
        if not supported(tournament):
            result.extend(db.query(models.Match).filter_by(tournament_id=tournament.id).all())
            continue
        players, nodes, _, _ = context(tournament, db)
        by_id = {p.id: p for p in players}
        for node in nodes.values():
            if not node["winner_id"]:
                continue
            pid1, pid2 = node["result_participants"]
            identity = -node["revision_id"] if node["revision_id"] else node["legacy_match_id"]
            result.append(SimpleNamespace(id=identity, tournament_id=tournament.id, tournament=tournament,
                attacker=by_id.get(pid1), defender=by_id.get(pid2), winner=by_id.get(node["winner_id"]), created_at=None,
                stage="Final" if node["remaining"] == 2 else f"Best {node['remaining']}",
                bracket_stage={8: "quarterfinal", 4: "semifinal", 2: "final"}.get(node["remaining"]) if tournament.registration_scope == "champion_8" else None,
                bracket_slot=node["slot"] if tournament.registration_scope == "champion_8" else None,
                attacker_id=pid1, defender_id=pid2, winner_id=node["winner_id"],
                round_results=[SimpleNamespace(match_id=identity, round_number=i+1, winner_id=pid) for i, pid in enumerate(node["rounds"])],
                arena_phase=node["result_phase"],
                arena_decks={pid: projected_deck(pid, teams, -pid) for pid, teams in zip(node["result_participants"], node["result_teams"])}))
    return result


def deck_for_match(match, player_id, db):
    if hasattr(match, "arena_decks"):
        return match.arena_decks.get(player_id)
    return db.query(models.DeckSet).filter_by(player_id=player_id).first()
