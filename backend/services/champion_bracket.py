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
