export interface SynergyCharacter {
  id: number;
  name?: string | null;
  burst_phase?: string | number | null;
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

export type SynergyBurstGroupKey = "1" | "2" | "3" | "A" | "other";

export interface SynergyCharacterGroup<T extends SynergyCharacter = SynergyCharacter> {
  key: SynergyBurstGroupKey;
  label: string;
  options: SynergyCharacterOption<T>[];
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

const SYNERGY_BURST_GROUPS: Array<Pick<SynergyCharacterGroup, "key" | "label">> = [
  { key: "1", label: "バースト1" },
  { key: "2", label: "バースト2" },
  { key: "3", label: "バースト3" },
  { key: "A", label: "バーストA" },
  { key: "other", label: "その他" },
];

export function normalizeSynergyBurst(value: unknown): SynergyBurstGroupKey {
  const normalized = String(value ?? "").trim().toUpperCase();
  return normalized === "1" || normalized === "2" || normalized === "3" || normalized === "A"
    ? normalized
    : "other";
}

export function groupSynergyCharacterOptions<T extends SynergyCharacter>(
  options: SynergyCharacterOption<T>[],
): SynergyCharacterGroup<T>[] {
  const byGroup = new Map<SynergyBurstGroupKey, SynergyCharacterOption<T>[]>();
  const seenIds = new Set<number>();
  for (const option of options) {
    const id = Number(option.character.id);
    if (seenIds.has(id)) continue;
    seenIds.add(id);
    const key = normalizeSynergyBurst(option.character.burst_phase);
    const group = byGroup.get(key) ?? [];
    group.push(option);
    byGroup.set(key, group);
  }
  return SYNERGY_BURST_GROUPS.flatMap(({ key, label }) => {
    const group = byGroup.get(key) ?? [];
    group.sort((left, right) => {
      const byName = japaneseCollator.compare(left.character.name ?? "", right.character.name ?? "");
      return byName || Number(left.character.id) - Number(right.character.id);
    });
    return group.length ? [{ key, label, options: group }] : [];
  });
}

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
