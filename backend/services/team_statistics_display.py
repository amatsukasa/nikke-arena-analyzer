"""Phase-local composition-set achievement, separate from commander finish.

Identify a formal set by its registration ID or a verified legacy league snapshot.
"""
from collections import Counter, defaultdict
import re
from services import arena_phases

RESULT_CODES = {'優勝': 'champion', '準優勝': 'runner_up', 'ベスト4': 'best4',
    'ベスト8': 'best8', 'ベスト16': 'best16', 'ベスト32': 'best32', 'ベスト64': 'best64'}
RESULT_ORDER = {'champion': 0, 'runner_up': 1, 'finalist': 2, 'best4': 3,
    'qualified_best8': 4, 'best8': 4, 'best16': 5, 'best32': 6, 'best64': 7}


def result_code(value):
    return value if value in RESULT_ORDER else RESULT_CODES.get(value)


def highest(values):
    known = {result_code(v) for v in values} - {None}
    return min(known, key=lambda v: (RESULT_ORDER[v], v)) if known else None


def canonical(team):
    ids = [getattr(team, f'char{i}_id', None) for i in range(1, 6)]
    return ','.join(map(str, sorted(ids))) if all(i is not None for i in ids) else None


def finish_counts(player_ids, result_by_player):
    # Retained for API compatibility; the UI no longer renders distributions.
    counts = Counter(result_by_player[p] for p in set(player_ids) if p in result_by_player)
    return [{'result': result, 'count': count} for result, count in sorted(counts.items())]


def achievement(match, player_id, phase, tournament):
    remaining = getattr(match, 'arena_remaining', None)
    if remaining is None:
        raw = re.fullmatch(r'Best\s+(64|32|16|8|4)', match.stage, re.I)
        remaining = int(raw[1]) if raw else 2 if match.stage.lower() == 'final' else None
    if remaining is None or match.winner_id not in (match.attacker_id, match.defender_id):
        return None
    if remaining == 2:
        return 'champion' if match.winner_id == player_id else 'runner_up'
    if match.winner_id != player_id:
        return f'best{remaining}'
    if remaining == 4:
        return 'finalist'
    if remaining == 16 and phase == 'initial' and tournament.registration_scope == 'full_64':
        return 'qualified_best8'
    return f'best{remaining // 2}'


def matches_registration(current, match, player_id, tournament, stored_phase):
    registration_ids = getattr(match, 'arena_registration_ids', {})
    if current is None or player_id not in registration_ids:
        return False
    stored_id = registration_ids[player_id]
    current_id = getattr(current, 'registration_id', None)
    if current_id is not None or stored_id is not None:
        return current_id is not None and current_id == stored_id
    if arena_phases.normalized_stage(tournament, stored_phase) != 'league':
        return False
    signature = getattr(current, 'legacy_initial_signature', None)
    saved_teams = getattr(match, 'arena_saved_teams', {}).get(player_id)
    return signature is not None and saved_teams is not None and signature == arena_phases.exact_set_signature(saved_teams)


def metadata(decks, matches, result_by_player, phase, tournaments, players):
    users, positions = defaultdict(set), defaultdict(set)
    keys_by_player = defaultdict(set)
    history, uncertain = defaultdict(Counter), set()
    decks_by_player = {d.player_id: d for d in decks}
    players_by_id = {p.id: p for p in players}
    set_results = defaultdict(list)
    for deck in decks:
        for team in deck.teams:
            key = canonical(team)
            if key:
                users[key].add(deck.player_id)
                keys_by_player[deck.player_id].add(key)
                positions[(key, team.team_number)].add(deck.player_id)
    for match in matches:
        tournament = tournaments.get(match.tournament_id)
        formal = bool(tournament and tournament.deck_registration_phases)
        stored_phase = arena_phases.stored_analysis_phase(tournament, phase) if formal else None
        if formal and getattr(match, 'arena_phase', 'initial') != stored_phase:
            continue
        snapshots = getattr(match, 'arena_decks', None)
        verified = snapshots is not None and getattr(match, 'arena_deck_history_verified', False)
        for player_id in (match.attacker_id, match.defender_id):
            current = decks_by_player.get(player_id)
            player = players_by_id.get(player_id)
            if (formal and verified and player is not None and player.tournament_id == match.tournament_id
                    and matches_registration(current, match, player_id, tournament, stored_phase)):
                value = achievement(match, player_id, stored_phase, tournament)
                if value:
                    set_results[player_id].append(value)
        if not verified:
            participants = {match.attacker_id, match.defender_id}
            for pid in participants:
                uncertain.update(keys_by_player[pid])
            continue
        for player_id in (match.attacker_id, match.defender_id):
            deck = snapshots.get(player_id)
            if deck is None:
                continue
            by_number = {team.team_number: team for team in deck.teams}
            for rr in match.round_results:
                if rr.winner_id is None:
                    continue
                team = by_number.get(rr.round_number)
                key = canonical(team) if team is not None else None
                if key:
                    history[key][match.stage] += 1
    data = {}
    for key, pids in users.items():
        format_flags = {bool(tournaments[players_by_id[pid].tournament_id].deck_registration_phases)
            for pid in pids if pid in players_by_id and players_by_id[pid].tournament_id in tournaments}
        formal = format_flags == {True}
        per_player = {pid: highest(set_results[pid]) if formal else result_code(result_by_player.get(pid)) for pid in pids}
        values = list(per_player.values())
        # If any set cannot be identified, its achievement is not replaced by
        # its commander's finish. Aggregate uncertainty remains explicit.
        composition = highest(values) if values and all(v is not None for v in values) and len(format_flags) == 1 else None
        # A known stage ceiling proves the aggregate maximum even if another
        # set is unknown; this does not invent a result for that unknown set.
        if composition is None and len(format_flags) == 1:
            known = highest(values)
            ceilings = []
            for pid, value in per_player.items():
                if value is not None:
                    continue
                tournament = tournaments.get(players_by_id[pid].tournament_id) if pid in players_by_id else None
                ceiling = ('champion' if not formal or phase == 'final' else
                    'qualified_best8' if arena_phases.stored_analysis_phase(tournament, phase) == 'initial' and tournament and tournament.registration_scope == 'full_64' else 'finalist')
                ceilings.append(RESULT_ORDER[ceiling])
            if known is not None and all(RESULT_ORDER[known] <= ceiling for ceiling in ceilings):
                composition = known
        stages = {arena_phases.normalized_stage(tournaments[players_by_id[pid].tournament_id],
            arena_phases.stored_analysis_phase(tournaments[players_by_id[pid].tournament_id], phase)) for pid in pids}
        display_stage = next(iter(stages)) if len(stages) == 1 else None
        data[key] = {
            'registration_phase': display_stage,
            'composition_best_result': composition,
            'commander_best_result': highest(result_by_player.get(pid) for pid in pids),
            'composition_result_status': 'known' if composition else 'undetermined',
            'usage_history': [{'stage': stage, 'round_count': count} for stage, count in sorted(history[key].items())],
            'usage_history_status': 'legacy_unverifiable' if key in uncertain else 'verified',
            'commander_results': finish_counts(pids, result_by_player),
            'position_composition_results': {str(pos): (highest(per_player[pid] for pid in positions[(key, pos)]) if positions[(key, pos)] and all(per_player[pid] is not None for pid in positions[(key, pos)]) else None) for pos in range(1, 6)},
            'position_commander_results': {str(pos): finish_counts(positions[(key, pos)], result_by_player) for pos in range(1, 6)},
        }
    return data


def annotate(teams, by_canonical, phase):
    for team in teams:
        data = by_canonical.get(team.get('canonical_id'), {})
        team.update({k: v for k, v in data.items() if k not in ('position_commander_results', 'position_composition_results')})
        team.setdefault('registration_phase', phase)
        team.setdefault('composition_best_result', None)
        team.setdefault('commander_best_result', result_code(team.get('best_result')))
        team.setdefault('composition_result_status', 'undetermined')
        team.setdefault('usage_history', [])
        team.setdefault('usage_history_status', 'unavailable')
        if not team.get('total_matches'):
            team['win_rate'] = None
        for position in team.get('position_stats', []):
            position['composition_best_result'] = data.get('position_composition_results', {}).get(str(position['position']))
            position['commander_results'] = data.get('position_commander_results', {}).get(str(position['position']), [])
    return teams


def filter_highest(teams, composition=None, commander=None):
    def matches(value, requested):
        if not requested:
            return True
        code = result_code(value)
        if requested == 'unknown':
            return code is None
        threshold = result_code(requested)
        return code is not None and threshold is not None and RESULT_ORDER[code] <= RESULT_ORDER[threshold]
    return [team for team in teams if matches(team.get('composition_best_result'), composition)
            and matches(team.get('commander_best_result') or team.get('best_result'), commander)]
