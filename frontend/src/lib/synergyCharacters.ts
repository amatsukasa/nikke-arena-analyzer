export interface SynergyCharacter {
  id: number;
  name?: string | null;
  [key: string]: unknown;
}

export interface CharacterUsageCount {
  id?: number;
  character_id?: number;
  count?: number;
  player_count?: number;
}

export interface SynergyCharacterOption<T extends SynergyCharacter = SynergyCharacter> {
  character: T;
  count: number;
  unavailable: boolean;
}

export interface SynergySelection {
  includedIds: number[];
  excludedIds: number[];
  addedAsExclusionDueToLimit?: boolean;
}

export function emptySynergySelection(): SynergySelection {
  return { includedIds: [], excludedIds: [] };
}

export function reconcileSynergySelection(
  includedIds: number[],
  excludedIds: number[],
  selectableIds: number[],
): SynergySelection {
  const selectable = new Set(selectableIds.map(Number));
  return {
    includedIds: includedIds.filter((id) => selectable.has(Number(id))),
    excludedIds: excludedIds.filter((id) => selectable.has(Number(id))),
  };
}

const japaneseCollator = new Intl.Collator("ja", {
  sensitivity: "base",
  numeric: true,
});

export function shouldResetSynergySelection(previousKey: string | null, nextKey: string | null): boolean {
  return previousKey !== null && nextKey !== null && previousKey !== nextKey;
}

export function transitionSynergySelection(
  characterId: number,
  includedIds: number[],
  excludedIds: number[],
  selectable = true,
): SynergySelection {
  if (!selectable || characterId === 9999) return { includedIds, excludedIds };
  if (includedIds.includes(characterId)) {
    return {
      includedIds: includedIds.filter((id) => id !== characterId),
      excludedIds: [...excludedIds.filter((id) => id !== characterId), characterId],
    };
  }
  if (excludedIds.includes(characterId)) {
    return {
      includedIds,
      excludedIds: excludedIds.filter((id) => id !== characterId),
    };
  }
  if (includedIds.length >= 5) {
    return {
      includedIds,
      excludedIds: [...excludedIds, characterId],
      addedAsExclusionDueToLimit: true,
    };
  }
  return { includedIds: [...includedIds, characterId], excludedIds };
}

export function teamMatchesSynergyConditions(
  teamCharacterIds: number[],
  includedIds: number[],
  excludedIds: number[],
): boolean {
  if (includedIds.length === 0) return false;
  const teamIds = new Set(teamCharacterIds.map(Number));
  return includedIds.every((id) => teamIds.has(Number(id)))
    && excludedIds.every((id) => !teamIds.has(Number(id)));
}

export function mapAndSortSynergyCharacters<T extends SynergyCharacter>(
  characters: T[],
  characterUsage: CharacterUsageCount[],
): SynergyCharacterOption<T>[] {
  const counts = new Map<number, number>();
  characterUsage.forEach((entry) => {
    const id = Number(entry.id ?? entry.character_id);
    if (!Number.isFinite(id)) return;
    counts.set(id, Number(entry.count ?? 0));
  });

  return characters
    .map((character) => {
      const count = counts.get(Number(character.id)) ?? 0;
      return { character, count, unavailable: count <= 0 };
    })
    .sort((left, right) => {
      if (left.count !== right.count) return right.count - left.count;
      const byName = japaneseCollator.compare(left.character.name ?? "", right.character.name ?? "");
      return byName || Number(left.character.id) - Number(right.character.id);
    });
}

export function mapAndSortSelectableSynergyCharacters<T extends SynergyCharacter>(
  characters: T[],
  characterUsage: CharacterUsageCount[],
): SynergyCharacterOption<T>[] {
  return mapAndSortSynergyCharacters(
    characters.filter((character) => Number(character.id) !== 9999),
    characterUsage,
  ).filter((option) => option.count > 0);
}
