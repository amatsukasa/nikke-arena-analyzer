"""Preview, apply, or roll back links for one official full64 tournament."""

import argparse
import json
from types import SimpleNamespace

from sqlalchemy import text

import models
from database import SessionLocal
from services import arena_phases
from services.team_statistics_display import achievement


def run(db, args):
    if args.action == "preview":
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    database = db.execute(text("SELECT current_database()")).scalar_one()
    if database != args.expect_database:
        raise ValueError("Connected database differs from --expect-database")
    query = db.query(models.Tournament).filter_by(id=args.tournament_id)
    if args.action != "preview":
        query = query.with_for_update(of=models.Tournament)
    tournament = query.one_or_none()
    if tournament is None or tournament.registration_scope != "full_64" or not arena_phases.supported(tournament):
        raise ValueError("Target must be an official full64 tournament")
    batch = db.get(models.ArenaLegacyLeagueLinkBatch, tournament.id)
    report = {"database": database, "tournament_id": tournament.id, "name": tournament.name,
              "active_digest": batch.digest if batch else None}
    if args.action == "rollback":
        if batch is None or batch.digest != args.digest:
            raise ValueError("No applied batch with the supplied digest")
        db.delete(batch)
        return {**report, "action": "rolled_back", "matches": len(batch.links)}

    _, nodes, _, _ = arena_phases.context(tournament, db)
    links = {}
    skipped = []
    achievements = {}
    for key, node in nodes.items():
        if node["legacy_match_id"] is None or node["remaining"] not in (64, 32, 16):
            continue
        link = arena_phases.legacy_league_link_input(node)
        if link is None:
            skipped.append({"match_key": key, "match_id": node["legacy_match_id"],
                            "reason": "Legacy participants, rounds or a complete unique initial deck could not be verified"})
            continue
        links[key] = link
        match = SimpleNamespace(arena_remaining=node["remaining"], winner_id=link["winner"],
                                attacker_id=link["participants"][0], defender_id=link["participants"][1])
        achievements[key] = {pid: achievement(match, pid, "initial", tournament) for pid in link["participants"]}
    digest = arena_phases.fingerprint({"schema": 1, "database": database,
                                     "tournament_id": tournament.id, "links": links, "skipped": skipped})
    summary = {**report, "digest": digest, "matches": len(links),
               "player_links": 2 * len(links), "skipped": skipped}
    if args.action == "preview":
        return {**summary, "action": "preview",
                "links": [{**link, "achievements": achievements[key]} for key, link in links.items()]}
    if not links or digest != args.digest:
        raise ValueError("No candidates, or preview changed. Run preview again")
    if batch is not None:
        if batch.digest == digest:
            return {**summary, "action": "already_applied"}
        raise ValueError("A different batch is already applied. Review and roll it back first")
    db.add(models.ArenaLegacyLeagueLinkBatch(id=tournament.id, digest=digest, operator=args.operator, links=links))
    return {**summary, "action": "applied"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "apply", "rollback"))
    parser.add_argument("--tournament-id", required=True, type=int)
    parser.add_argument("--expect-database", required=True)
    parser.add_argument("--digest")
    parser.add_argument("--operator", help="Name or work ticket of the administrator applying the batch")
    args = parser.parse_args()
    if args.action != "preview" and not args.digest:
        parser.error("apply and rollback require --digest from the reviewed preview")
    if args.action == "apply" and (not args.operator or not 1 <= len(args.operator.strip()) <= 120):
        parser.error("apply requires a nonempty --operator of at most 120 characters")
    try:
        with SessionLocal.begin() as db:
            report = run(db, args)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
