export const CHAMPION_ARENA_STORAGE_KEY = "nikkeari_championship_results_v1";
export const LEGACY_ARENA_STORAGE_KEY = "nikkeari_user_data_v1";

export const arenaResultLabels = {
  not_entered: "未入力", not_participated: "未出場", unknown: "不明",
  league_loss: "リーグ敗退", best64: "BEST64", best32: "BEST32",
  best16: "BEST16", best8: "BEST8", best4: "BEST4",
  runner_up: "準優勝", champion: "優勝",
} as const;

export type ArenaResult = keyof typeof arenaResultLabels;
export type ArenaTournament = {
  id: string;
  title: string;
  display_order: number | null;
  event_date?: string | null;
  source?: "championship" | "legacy_tournament";
  tournament_id?: number | null;
  legacy_tournament_ids?: number[];
};
export type StoredArenaResult = {
  result: ArenaResult;
  titleSnapshot: string;
  reviewedLegacyResults?: Record<string, ArenaResult>;
};
export type UserDataV1 = { version:1; championArena:{ results:Record<string, StoredArenaResult> } };
export type ArenaResultEntry = {
  tournament: ArenaTournament;
  result: ArenaResult;
  conflicts: ArenaResult[];
  legacyResults: Record<string, ArenaResult>;
};

const participated = new Set<ArenaResult>(["unknown","league_loss","best64","best32","best16","best8","best4","runner_up","champion"]);
const ranked: ArenaResult[] = ["league_loss","best64","best32","best16","best8","best4","runner_up","champion"];

export function emptyUserData(): UserDataV1 { return { version:1, championArena:{ results:{} } }; }
export function loadUserData(storage: Pick<Storage, "getItem">, key = CHAMPION_ARENA_STORAGE_KEY): UserDataV1 {
  try {
    const parsed = JSON.parse(storage.getItem(key) || "null");
    const results = parsed?.championArena?.results;
    if (parsed?.version === 1 && results && typeof results === "object" && !Array.isArray(results)) return parsed;
  } catch {}
  return emptyUserData();
}

function readResult(record: StoredArenaResult | undefined): ArenaResult | undefined {
  const value = record?.result;
  return typeof value === "string" && Object.hasOwn(arenaResultLabels, value) ? value : undefined;
}

function resolveArenaEntry(
  tournament: ArenaTournament,
  current: Record<string, StoredArenaResult>,
  old: Record<string, StoredArenaResult>,
): ArenaResultEntry {
  const legacyResults: Record<string, ArenaResult> = {};
  const tournamentIds = tournament.source === "legacy_tournament" && tournament.tournament_id != null
    ? [tournament.tournament_id]
    : tournament.legacy_tournament_ids ?? [];
  for (const id of tournamentIds) {
    const legacyKey = `legacy-tournament:${id}`;
    const numericKey = `tournament:${id}`;
    const linked = legacyKey === tournament.id ? undefined : current[legacyKey];
    const linkedResult = readResult(linked);
    if (linkedResult === "not_entered") continue;
    if (linkedResult) legacyResults[legacyKey] = linkedResult;
    const oldResult = readResult(old[String(id)]);
    if (oldResult && oldResult !== "not_entered" && linked?.reviewedLegacyResults?.[numericKey] !== oldResult) {
      legacyResults[numericKey] = oldResult;
    }
  }

  const saved = current[tournament.id];
  const savedResult = readResult(saved);
  // Clearing a result on the previous UI was also an explicit saved choice.
  if (savedResult === "not_entered" && !saved?.reviewedLegacyResults) {
    return { tournament, result: savedResult, conflicts: [], legacyResults };
  }
  const values = new Set<ArenaResult>();
  if (savedResult) values.add(savedResult);
  for (const [key, value] of Object.entries(legacyResults)) {
    if (saved?.reviewedLegacyResults?.[key] !== value) values.add(value);
  }
  const conflicts = values.size > 1 ? [...values] : [];
  const result = conflicts.length ? "not_entered" : values.values().next().value ?? "not_entered";
  return { tournament, result, conflicts, legacyResults };
}

export function resolveArenaEntries(tournaments: ArenaTournament[], current: UserDataV1, old: UserDataV1) {
  // The API owns the display order. Both the form and the stats use these entries.
  return tournaments.map(tournament => resolveArenaEntry(tournament, current.championArena.results, old.championArena.results));
}

export function saveArenaResult(storage: Pick<Storage, "getItem" | "setItem">, entry: ArenaResultEntry, result: ArenaResult) {
  const data = loadUserData(storage);
  const updated: UserDataV1 = {
    ...data,
    championArena: {
      ...data.championArena,
      results: {
        ...data.championArena.results,
        [entry.tournament.id]: { result, titleSnapshot: entry.tournament.title, reviewedLegacyResults: entry.legacyResults },
      },
    },
  };
  storage.setItem(CHAMPION_ARENA_STORAGE_KEY, JSON.stringify(updated));
  return updated;
}

export function compareArenaResults(left:ArenaResult, right:ArenaResult) { return ranked.indexOf(left) - ranked.indexOf(right); }
export function calculateChampionArenaStats(entries: ArenaResultEntry[]) {
  const appearances = entries.filter(entry=>participated.has(entry.result));
  const known = appearances.filter(entry=>ranked.includes(entry.result));
  const best = known.reduce<typeof known[number] | null>((current,entry)=>!current || compareArenaResults(entry.result,current.result)>0?entry:current,null);
  return {
    appearanceCount: appearances.length,
    knownCount: known.length,
    unknownCount: appearances.filter(entry=>entry.result==="unknown").length,
    bestResult: best?.result ?? null,
    latest: entries.find(entry => entry.result !== "not_entered") ?? null,
  };
}
