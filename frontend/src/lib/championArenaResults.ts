export const CHAMPION_ARENA_STORAGE_KEY = "nikkeari_user_data_v1";

export const arenaResultLabels = {
  not_entered: "未入力", not_participated: "未出場", unknown: "不明",
  league_loss: "リーグ敗退", best64: "BEST64", best32: "BEST32",
  best16: "BEST16", best8: "BEST8", best4: "BEST4",
  runner_up: "準優勝", champion: "優勝",
} as const;

export type ArenaResult = keyof typeof arenaResultLabels;
export type ArenaTournament = { id:number; title:string; display_order:number|null; game_start_date:string|null };
export type StoredArenaResult = { result:ArenaResult; titleSnapshot:string };
export type UserDataV1 = { version:1; championArena:{ results:Record<string, StoredArenaResult> } };

const participated = new Set<ArenaResult>(["unknown","league_loss","best64","best32","best16","best8","best4","runner_up","champion"]);
const ranked: ArenaResult[] = ["league_loss","best64","best32","best16","best8","best4","runner_up","champion"];

export function emptyUserData(): UserDataV1 { return { version:1, championArena:{ results:{} } }; }
export function loadUserData(storage: Pick<Storage,"getItem">): UserDataV1 {
  try {
    const parsed = JSON.parse(storage.getItem(CHAMPION_ARENA_STORAGE_KEY) || "null");
    if (parsed?.version === 1 && parsed.championArena?.results && typeof parsed.championArena.results === "object") return parsed;
  } catch {}
  return emptyUserData();
}
export function compareArenaResults(left:ArenaResult, right:ArenaResult) { return ranked.indexOf(left) - ranked.indexOf(right); }
export function calculateChampionArenaStats(tournaments:ArenaTournament[], results:Record<string,StoredArenaResult>) {
  const ordered = [...tournaments].sort((a,b)=>(b.display_order ?? -Infinity)-(a.display_order ?? -Infinity)
    || (b.game_start_date ? Date.parse(b.game_start_date) : -Infinity) - (a.game_start_date ? Date.parse(a.game_start_date) : -Infinity)
    || b.id-a.id);
  const entries = ordered.map(tournament=>({ tournament, result:results[String(tournament.id)]?.result ?? "not_entered" as ArenaResult }));
  const appearances = entries.filter(entry=>participated.has(entry.result));
  const known = appearances.filter(entry=>ranked.includes(entry.result));
  const best = known.reduce<typeof known[number] | null>((current,entry)=>!current || compareArenaResults(entry.result,current.result)>0?entry:current,null);
  return {
    appearanceCount: appearances.length,
    knownCount: known.length,
    unknownCount: appearances.filter(entry=>entry.result==="unknown").length,
    bestResult: best?.result ?? null,
    latest: appearances[0] ?? null,
  };
}
