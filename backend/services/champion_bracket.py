"""Pure champion-eight bracket structure and dependency helpers."""

from dataclasses import dataclass


BracketKey = tuple[str, int]


@dataclass(frozen=True)
class BracketSlotDefinition:
    key: BracketKey
    name: str
    left_slot: int | None = None
    right_slot: int | None = None
    upstream: tuple[BracketKey, ...] = ()


CHAMPION_BRACKET: tuple[BracketSlotDefinition, ...] = (
    BracketSlotDefinition(("quarterfinal", 1), "QF1", 1, 2),
    BracketSlotDefinition(("quarterfinal", 2), "QF2", 3, 4),
    BracketSlotDefinition(("quarterfinal", 3), "QF3", 5, 6),
    BracketSlotDefinition(("quarterfinal", 4), "QF4", 7, 8),
    BracketSlotDefinition(("semifinal", 1), "SF1", upstream=(("quarterfinal", 1), ("quarterfinal", 2))),
    BracketSlotDefinition(("semifinal", 2), "SF2", upstream=(("quarterfinal", 3), ("quarterfinal", 4))),
    BracketSlotDefinition(("final", 1), "Final", upstream=(("semifinal", 1), ("semifinal", 2))),
)

CHAMPION_BRACKET_BY_KEY = {definition.key: definition for definition in CHAMPION_BRACKET}
CHAMPION_DEPENDENTS: dict[BracketKey, tuple[BracketKey, ...]] = {
    ("quarterfinal", 1): (("semifinal", 1),),
    ("quarterfinal", 2): (("semifinal", 1),),
    ("quarterfinal", 3): (("semifinal", 2),),
    ("quarterfinal", 4): (("semifinal", 2),),
    ("semifinal", 1): (("final", 1),),
    ("semifinal", 2): (("final", 1),),
    ("final", 1): (),
}


def get_bracket_definition(stage: str, slot: int) -> BracketSlotDefinition | None:
    return CHAMPION_BRACKET_BY_KEY.get((stage, slot))


def participant_ids(
    definition: BracketSlotDefinition,
    player_ids_by_slot: dict[int, int],
    winner_ids_by_match: dict[BracketKey, int],
) -> tuple[int | None, int | None]:
    if definition.upstream:
        return tuple(winner_ids_by_match.get(key) for key in definition.upstream)  # type: ignore[return-value]
    return (
        player_ids_by_slot.get(definition.left_slot),
        player_ids_by_slot.get(definition.right_slot),
    )


def dependent_keys(key: BracketKey) -> tuple[BracketKey, ...]:
    return CHAMPION_DEPENDENTS[key]


def match_is_complete(match, expected_participants=None) -> bool:
    """Pure completeness rule shared by bracket state and publication checks."""
    if match is None or match.winner_id is None:
        return False
    participants = (match.attacker_id, match.defender_id)
    if expected_participants is not None and participants != expected_participants:
        return False
    if participants[0] is None or participants[1] is None or participants[0] == participants[1]:
        return False
    rounds = list(match.round_results)
    if len(rounds) != 5 or sorted(result.round_number for result in rounds) != [1, 2, 3, 4, 5]:
        return False
    if any(result.winner_id not in participants for result in rounds):
        return False
    attacker_wins = sum(result.winner_id == participants[0] for result in rounds)
    calculated_winner = participants[0] if attacker_wins >= 3 else participants[1]
    return match.winner_id == calculated_winner
