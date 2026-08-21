"""Side-effect-free tournament result calculation shared by all aggregations."""

from services.champion_bracket import CHAMPION_BRACKET, match_is_complete, participant_ids


RESULT_LABELS = {
    "best64": "ベスト64",
    "best32": "ベスト32",
    "best16": "ベスト16",
    "best8": "ベスト8",
    "best4": "ベスト4",
    "runner_up": "準優勝",
    "champion": "優勝",
}
RESULT_SCORES = {code: score for code, score in (
    ("best64", 64), ("best32", 32), ("best16", 16), ("best8", 8),
    ("best4", 4), ("runner_up", 2), ("champion", 1),
)}


def result_label(code):
    return RESULT_LABELS.get(code, "不明")


def _valid_winner_by_pair(matches):
    winners = {}
    for match in matches:
        participants = (match.attacker_id, match.defender_id)
        if (
            participants[0] is not None
            and participants[1] is not None
            and participants[0] != participants[1]
            and match.winner_id in participants
        ):
            winners[frozenset(participants)] = match.winner_id
    return winners


def _full64_results(players, matches):
    results = {player.id: "best64" for player in players}
    by_seed = {player.seed_number: player for player in players if player.seed_number is not None}
    winners = _valid_winner_by_pair(matches)

    def winner_between(left, right):
        if left is None or right is None:
            return None
        return winners.get(frozenset((left, right)))

    group_winners = []
    for group_index in range(8):
        base = group_index * 8
        first_winners = []
        for pair in range(4):
            left = by_seed.get(base + pair * 2 + 1)
            right = by_seed.get(base + pair * 2 + 2)
            winner = winner_between(left.id if left else None, right.id if right else None)
            first_winners.append(winner)
            if winner is not None:
                results[winner] = "best32"
        semifinal_winners = [
            winner_between(first_winners[0], first_winners[1]),
            winner_between(first_winners[2], first_winners[3]),
        ]
        for winner in semifinal_winners:
            if winner is not None:
                results[winner] = "best16"
        group_winner = winner_between(semifinal_winners[0], semifinal_winners[1])
        if group_winner is not None:
            results[group_winner] = "best8"
        group_winners.append(group_winner)

    quarterfinal_winners = []
    for index in range(0, 8, 2):
        winner = winner_between(group_winners[index], group_winners[index + 1])
        quarterfinal_winners.append(winner)
        if winner is not None:
            results[winner] = "best4"
    finalists = []
    for index in range(0, 4, 2):
        winner = winner_between(quarterfinal_winners[index], quarterfinal_winners[index + 1])
        finalists.append(winner)
        if winner is not None:
            results[winner] = "runner_up"
    champion = winner_between(finalists[0], finalists[1])
    if champion is not None:
        results[champion] = "champion"
    return results


def _champion8_results(players, matches):
    results = {player.id: "best8" for player in players}
    players_by_slot = {
        player.champion_slot: player.id
        for player in players
        if player.champion_slot in range(1, 9)
    }
    matches_by_key = {
        (match.bracket_stage, match.bracket_slot): match
        for match in matches
        if match.bracket_stage is not None and match.bracket_slot is not None
    }
    winners = {}
    for definition in CHAMPION_BRACKET:
        expected = participant_ids(definition, players_by_slot, winners)
        match = matches_by_key.get(definition.key)
        if not match_is_complete(match, expected):
            continue
        winners[definition.key] = match.winner_id
        if definition.key[0] == "quarterfinal":
            results[match.winner_id] = "best4"
        elif definition.key[0] == "semifinal":
            results[match.winner_id] = "runner_up"
        else:
            results[match.winner_id] = "champion"
    return results


def calculate_player_results(tournament, players, matches):
    if tournament.registration_scope == "champion_8":
        return _champion8_results(players, matches)
    return _full64_results(players, matches)
