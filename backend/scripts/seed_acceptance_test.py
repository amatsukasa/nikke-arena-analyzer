"""Create reproducible, production-shaped local acceptance data.

This script is destructive by design and therefore accepts only the explicit
local Docker acceptance database allowlist.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
import os
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database_safety import validate_acceptance_database_url  # noqa: E402


def acceptance_database_url() -> str:
    try:
        return validate_acceptance_database_url(
            os.environ.get("ACCEPTANCE_DATABASE_URL"),
            os.environ.get("TEST_DATABASE_URL"),
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


os.environ["DATABASE_URL"] = acceptance_database_url()

from auth import hash_password  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
import models  # noqa: E402


CHARACTER_CSV = BACKEND_DIR / "testdata" / "characters_production.csv"
ARENA_CHARACTER_IDS = {19, 32, 33, 47, 52, 69, 103, 122, 145, 147, 162, 172}


def optional(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def load_characters() -> list[models.Character]:
    with CHARACTER_CSV.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows or any(not row.get("id") or not row.get("name") for row in rows):
        raise SystemExit("Character CSV is empty or invalid")
    return [
        models.Character(
            id=int(row["id"]),
            name=row["name"].strip(),
            rarity=optional(row["rarity"]),
            weapon=optional(row["weapon"]),
            element=optional(row["element"]),
            burst_phase=optional(row["burst_phase"]),
            manufacturer=optional(row["manufacturer"]),
            class_type=optional(row["class_type"]),
            is_arena_relevant=int(row["id"]) in ARENA_CHARACTER_IDS,
            is_template_available=row["is_template_available"].strip().lower() in {"t", "true", "1"},
            template_filename=optional(row["template_filename"]),
        )
        for row in rows
    ]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        table_names = [connection.dialect.identifier_preparer.format_table(table)
                       for table in Base.metadata.sorted_tables]
        connection.exec_driver_sql(
            f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE"
        )

    db = SessionLocal()
    try:
        characters = load_characters()
        db.add_all(characters)

        admin = models.AppUser(
            email="acceptance-admin@example.test",
            hashed_password=hash_password("acceptance-admin-password"),
            role="admin",
            provider_name="Acceptance Test Operator",
            game_start_date=date(2022, 11, 4),
            play_server="JP",
            approval_status="active",
            approved_at=datetime.now(timezone.utc),
        )
        db.add(admin)
        db.flush()

        championship = models.Championship(
            name="2026 Acceptance Championship",
            date=date(2026, 9, 17),
            start_date=date(2026, 9, 17),
            owner_name="Acceptance Test Operator",
            created_by=admin.id,
        )
        db.add(championship)
        db.flush()

        tournament = models.Tournament(
            name="2026-09 Team Search Acceptance Tournament",
            date=date(2026, 9, 17),
            season="2026-09 Acceptance",
            owner_name="Acceptance Test Operator",
            championship_id=championship.id,
            publication_status="draft",
            registration_scope="full_64",
            provider_game_start_date=date(2022, 11, 4),
            game_start_date=date(2022, 11, 4),
            display_order=1,
            is_champion_arena=True,
            has_match_data=True,
            created_by=admin.id,
        )
        db.add(tournament)
        db.flush()

        usable_ids = [character.id for character in characters if character.id != 9999]
        players: list[models.Player] = []
        for seed_number in range(1, 9):
            player = models.Player(
                tournament_id=tournament.id,
                seed_number=seed_number,
                name=f"Player {seed_number}",
            )
            db.add(player)
            db.flush()
            players.append(player)

            deck_set = models.DeckSet(player_id=player.id)
            db.add(deck_set)
            db.flush()
            offset = (seed_number - 1) * 25
            selected_ids = [usable_ids[(offset + index) % len(usable_ids)] for index in range(25)]
            for team_index in range(5):
                ids = selected_ids[team_index * 5:(team_index + 1) * 5]
                db.add(models.DeckTeam(
                    deck_set_id=deck_set.id,
                    team_number=team_index + 1,
                    char1_id=ids[0], char2_id=ids[1], char3_id=ids[2],
                    char4_id=ids[3], char5_id=ids[4],
                    collection1="sr_15", collection2="sr_15", collection3="sr_15",
                    collection4="sr_15", collection5="sr_15",
                ))

        db.flush()
        for match_index in range(4):
            attacker = players[match_index * 2]
            defender = players[match_index * 2 + 1]
            match = models.Match(
                tournament_id=tournament.id,
                stage="Best 64",
                attacker_id=attacker.id,
                defender_id=defender.id,
                winner_id=attacker.id,
            )
            db.add(match)
            db.flush()
            for round_number in range(1, 6):
                winner = attacker if round_number <= 3 else defender
                db.add(models.RoundResult(
                    match_id=match.id,
                    round_number=round_number,
                    winner_id=winner.id,
                ))

        db.commit()
        print(
            f"Seeded acceptance database: {len(characters)} characters, "
            f"{len(players)} players, 40 teams, 4 matches"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
