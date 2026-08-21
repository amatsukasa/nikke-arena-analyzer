"""Side-effect-free publication validation for champion-eight tournaments."""

from collections import Counter

from models import Character, DeckSet, DeckTeam, Match, Player, RoundResult
from services.champion_bracket import CHAMPION_BRACKET, match_is_complete, participant_ids


def _issue(code: str, message: str, **context):
    return {"code": code, "message": message, **context}


def validate_champion_publication(tournament, db):
    """Inspect persisted data without writes, flushes, commits, or cache effects."""
    errors = []
    warnings = []
    invalid_slots = []
    invalid_match_slots = []

    players = db.query(Player).filter(Player.tournament_id == tournament.id).all()
    slotted = [player for player in players if player.champion_slot is not None]
    slot_counts = Counter(player.champion_slot for player in slotted)
    invalid_slots = sorted(
        slot for slot, count in slot_counts.items() if slot not in range(1, 9) or count != 1
    )
    missing_slots = [slot for slot in range(1, 9) if slot_counts.get(slot, 0) != 1]
    if tournament.registration_scope != "champion_8":
        errors.append(_issue("invalid_registration_scope", "This validation is only available for champion_8 tournaments."))
    if missing_slots or invalid_slots:
        errors.append(_issue("invalid_champion_slots", "Champion slots 1 through 8 must each contain exactly one player.", slots=sorted(set(missing_slots + invalid_slots))))
    if len(slotted) != 8:
        errors.append(_issue("invalid_slotted_player_count", "Exactly 8 champion-slot players are required.", actual=len(slotted)))
    unslotted = [player.id for player in players if player.champion_slot is None]
    if unslotted:
        errors.append(_issue("unexpected_unslotted_players", "champion_8 tournaments cannot contain players without a champion slot.", count=len(unslotted)))

    known_seeds = [player.seed_number for player in players if player.seed_number is not None]
    invalid_seeds = sorted({seed for seed in known_seeds if seed not in range(1, 65)})
    duplicate_seeds = sorted(seed for seed, count in Counter(known_seeds).items() if count > 1)
    if invalid_seeds:
        errors.append(_issue("invalid_seed_numbers", "seed_number must be null or between 1 and 64.", seeds=invalid_seeds))
    if duplicate_seeds:
        errors.append(_issue("duplicate_seed_numbers", "Known seed numbers must be unique within the tournament.", seeds=duplicate_seeds))

    players_by_slot = {}
    players_by_id = {player.id: player for player in players}
    for player in slotted:
        if slot_counts[player.champion_slot] == 1 and player.champion_slot in range(1, 9):
            players_by_slot[player.champion_slot] = player.id
        expected_name = f"Player {player.seed_number}" if player.seed_number is not None else f"champion_slot_{player.champion_slot}"
        if player.name != expected_name:
            errors.append(_issue("invalid_player_name", "Player name does not match the champion naming rule.", player_id=player.id))

    player_ids = list(players_by_id)
    deck_sets = db.query(DeckSet).filter(DeckSet.player_id.in_(player_ids)).all() if player_ids else []
    sets_by_player = {}
    for deck_set in deck_sets:
        sets_by_player.setdefault(deck_set.player_id, []).append(deck_set)
    deck_set_ids = [deck_set.id for deck_set in deck_sets]
    teams = db.query(DeckTeam).filter(DeckTeam.deck_set_id.in_(deck_set_ids)).all() if deck_set_ids else []
    teams_by_set = {}
    for team in teams:
        teams_by_set.setdefault(team.deck_set_id, []).append(team)
    referenced_characters = set()
    character_ids_by_player = {}
    complete_player_ids = set()
    complete_players = 0
    for player in players:
        player_valid = True
        player_sets = sets_by_player.get(player.id, [])
        if len(player_sets) != 1:
            errors.append(_issue("invalid_deck_set_count", "Each player must have exactly one DeckSet.", player_id=player.id, actual=len(player_sets)))
            player_valid = False
            continue
        player_teams = teams_by_set.get(player_sets[0].id, [])
        numbers = [team.team_number for team in player_teams]
        if len(player_teams) != 5 or sorted(numbers) != [1, 2, 3, 4, 5]:
            errors.append(_issue("invalid_team_numbers", "Each DeckSet must contain team_number 1 through 5 exactly once.", player_id=player.id))
            player_valid = False
        character_ids = []
        for team in player_teams:
            slots = [getattr(team, f"char{index}_id") for index in range(1, 6)]
            if len(slots) != 5 or any(character_id is None for character_id in slots):
                errors.append(_issue("unresolved_team_characters", "Every team must contain five resolved characters.", player_id=player.id, team_number=team.team_number))
                player_valid = False
            character_ids.extend(character_id for character_id in slots if character_id is not None)
        referenced_characters.update(character_ids)
        character_ids_by_player[player.id] = set(character_ids)
        if len(character_ids) != 25 or len(set(character_ids)) != 25:
            errors.append(_issue("duplicate_player_characters", "A player's 25 character slots must be unique.", player_id=player.id))
            player_valid = False
        if player_valid:
            complete_player_ids.add(player.id)

    existing_characters = {
        row[0] for row in db.query(Character.id).filter(Character.id.in_(referenced_characters)).all()
    } if referenced_characters else set()
    missing_characters = sorted(referenced_characters - existing_characters)
    if missing_characters:
        errors.append(_issue("unknown_characters", "One or more character IDs do not exist.", character_ids=missing_characters))
        complete_player_ids = {
            player_id for player_id in complete_player_ids
            if not (character_ids_by_player.get(player_id, set()) & set(missing_characters))
        }
    complete_players = len(complete_player_ids)

    matches = db.query(Match).filter(Match.tournament_id == tournament.id).all()
    bracket_matches = [match for match in matches if match.bracket_stage is not None or match.bracket_slot is not None]
    expected_keys = {definition.key for definition in CHAMPION_BRACKET}
    key_counts = Counter((match.bracket_stage, match.bracket_slot) for match in bracket_matches)
    invalid_match_slots = sorted(
        [list(key) for key, count in key_counts.items() if key not in expected_keys or count != 1],
        key=lambda value: (str(value[0]), value[1] if isinstance(value[1], int) else -1),
    )
    missing_match_slots = [list(key) for key in expected_keys if key_counts.get(key, 0) != 1]
    if missing_match_slots or invalid_match_slots or len(bracket_matches) != 7:
        errors.append(_issue("invalid_match_slots", "The fixed 7 champion match slots must each exist exactly once.", slots=missing_match_slots + invalid_match_slots))

    matches_by_key = {}
    for match in bracket_matches:
        key = (match.bracket_stage, match.bracket_slot)
        if key in expected_keys and key_counts[key] == 1:
            matches_by_key[key] = match
    winner_ids = {}
    total_rounds = 0
    all_matches_complete = True
    for definition in CHAMPION_BRACKET:
        match = matches_by_key.get(definition.key)
        if match is None:
            all_matches_complete = False
            continue
        expected = participant_ids(definition, players_by_slot, winner_ids)
        if (match.attacker_id, match.defender_id) != expected or None in expected or match.attacker_id == match.defender_id:
            errors.append(_issue("invalid_match_participants", "Match participants do not match the fixed left/right bracket structure.", bracket_stage=definition.key[0], bracket_slot=definition.key[1]))
            all_matches_complete = False
        rounds = db.query(RoundResult).filter(RoundResult.match_id == match.id).all()
        total_rounds += len(rounds)
        numbers = [result.round_number for result in rounds]
        participants = {match.attacker_id, match.defender_id}
        if len(rounds) != 5 or sorted(numbers) != [1, 2, 3, 4, 5]:
            errors.append(_issue("invalid_round_numbers", "Each match must contain round_number 1 through 5 exactly once.", match_id=match.id))
            all_matches_complete = False
        if any(result.winner_id not in participants for result in rounds):
            errors.append(_issue("invalid_round_winner", "Every round winner must be one of the match participants.", match_id=match.id))
            all_matches_complete = False
        if len(rounds) == 5 and all(result.winner_id in participants for result in rounds):
            attacker_wins = sum(result.winner_id == match.attacker_id for result in rounds)
            majority = match.attacker_id if attacker_wins >= 3 else match.defender_id
            if match.winner_id != majority:
                errors.append(_issue("invalid_match_winner", "Match winner must equal the five-round majority winner.", match_id=match.id))
                all_matches_complete = False
            elif (match.attacker_id, match.defender_id) == expected:
                winner_ids[definition.key] = match.winner_id
        if not match_is_complete(match, expected):
            all_matches_complete = False

    if len(matches) != 7:
        errors.append(_issue("unexpected_matches", "champion_8 tournaments must contain exactly 7 matches.", actual=len(matches)))
    if total_rounds != 35:
        errors.append(_issue("invalid_round_result_count", "champion_8 tournaments must contain exactly 35 round results.", actual=total_rounds))
    if not all_matches_complete or len(winner_ids) != 7:
        errors.append(_issue("bracket_not_complete", "The tournament does not satisfy the champion bracket complete state."))

    counts = {
        "players": len(players),
        "complete_players": complete_players,
        "teams": len(teams),
        "matches": len(matches),
        "round_results": total_rounds,
    }
    if counts != {"players": 8, "complete_players": 8, "teams": 40, "matches": 7, "round_results": 35}:
        errors.append(_issue("invalid_total_counts", "A publishable tournament requires 8 players, 40 teams, 7 matches, and 35 round results.", **counts))
    return {
        "can_publish": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": counts,
        "invalid_slots": sorted(set(missing_slots + invalid_slots)),
        "invalid_match_slots": missing_match_slots + invalid_match_slots,
        # Preserve the existing publication-readiness response contract used by
        # the current management UI while exposing richer champion counts.
        "player_count": len(players),
        "complete_player_count": complete_players,
        "incomplete_player_count": len(players) - complete_players,
        "unresolved_slot_count": sum(
            getattr(team, f"char{index}_id") is None
            for team in teams for index in range(1, 6)
        ),
        "match_count": len(matches),
    }
