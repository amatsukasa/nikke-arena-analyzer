"""Champion-eight-only snapshot corrections over the legacy raw statistics."""

from models import DeckSet, Match, Player, Tournament
from services.tournament_results import calculate_player_results, result_label


RESULT_SCORE = {"優勝": 1, "準優勝": 2, "ベスト4": 4, "ベスト8": 8}


def champion_player_results(tournament_id, db):
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).one()
    players = db.query(Player).filter(Player.tournament_id == tournament_id).all()
    matches = db.query(Match).filter(Match.tournament_id == tournament_id).all()
    return {
        player_id: result_label(code)
        for player_id, code in calculate_player_results(tournament, players, matches).items()
    }


def _best_result(player_ids, results):
    values = [results[player_id] for player_id in player_ids if player_id in results]
    return min(values, key=lambda value: RESULT_SCORE[value]) if values else None


def enrich_champion_snapshot_stats(stats, tournament_id, db):
    """Correct result labels and add round matchups without commits or Sessions."""
    results = champion_player_results(tournament_id, db)
    players = db.query(Player).filter(Player.tournament_id == tournament_id).all()
    players_by_id = {player.id: player for player in players}
    players_by_name = {player.name: player for player in players}
    deck_sets = db.query(DeckSet).filter(DeckSet.player_id.in_(list(results))).all()
    players_by_team = {}
    players_by_team_position = {}
    players_by_character = {}
    players_by_character_team_position = {}
    for deck_set in deck_sets:
        for team in deck_set.teams:
            character_ids = [getattr(team, f"char{index}_id") for index in range(1, 6)]
            canonical = ",".join(map(str, sorted(character_ids)))
            players_by_team.setdefault(canonical, set()).add(deck_set.player_id)
            players_by_team_position.setdefault((canonical, team.team_number), set()).add(deck_set.player_id)
            for character_id in character_ids:
                players_by_character.setdefault(character_id, set()).add(deck_set.player_id)
                players_by_character_team_position.setdefault((character_id, team.team_number), set()).add(deck_set.player_id)

    for character in stats.get("character_stats", []):
        character_id = character.get("id")
        character["best_result"] = _best_result(players_by_character.get(character_id, set()), results)
        for position in character.get("team_position_stats", []):
            position["best_result"] = _best_result(
                players_by_character_team_position.get((character_id, position.get("position")), set()), results
            )
    for team in stats.get("team_usage", []):
        canonical = team.get("canonical_id")
        team["best_result"] = _best_result(players_by_team.get(canonical, set()), results)
        for adopted in team.get("adopted_players", []):
            player = players_by_name.get(adopted.get("player_name"))
            if player:
                adopted["result"] = results[player.id]
        for position in team.get("position_stats", []):
            position["best_result"] = _best_result(
                players_by_team_position.get((canonical, position.get("position")), set()), results
            )

    matchups = []
    matches = db.query(Match).filter(Match.tournament_id == tournament_id).all()
    sets_by_player = {deck_set.player_id: deck_set for deck_set in deck_sets}
    for match in matches:
        attacker_set = sets_by_player.get(match.attacker_id)
        defender_set = sets_by_player.get(match.defender_id)
        if not attacker_set or not defender_set:
            continue
        attacker_teams = {team.team_number: team for team in attacker_set.teams}
        defender_teams = {team.team_number: team for team in defender_set.teams}
        for round_result in match.round_results:
            attacker_team = attacker_teams.get(round_result.round_number)
            defender_team = defender_teams.get(round_result.round_number)
            if not attacker_team or not defender_team:
                continue
            left = [getattr(attacker_team, f"char{index}_id") for index in range(1, 6)]
            right = [getattr(defender_team, f"char{index}_id") for index in range(1, 6)]
            attacker_won = round_result.winner_id == match.attacker_id
            matchups.append({
                "match_id": match.id,
                "round_number": round_result.round_number,
                "stage": match.stage,
                "attacker_team": left,
                "defender_team": right,
                "canonical_attacker": ",".join(map(str, sorted(left))),
                "canonical_defender": ",".join(map(str, sorted(right))),
                "winner_team": left if attacker_won else right,
                "loser_team": right if attacker_won else left,
                "winner_is_attacker": attacker_won,
                "tournament_id": tournament_id,
                "attacker_name": players_by_id[match.attacker_id].name,
                "defender_name": players_by_id[match.defender_id].name,
            })
    stats["matchups"] = matchups
    return stats
