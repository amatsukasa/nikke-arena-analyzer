export type ChampionProxyAction = "teams" | "analyze-deck" | "icon";
const ACTION_METHODS: Record<ChampionProxyAction, ReadonlySet<string>> = { teams: new Set(["GET", "PUT"]), "analyze-deck": new Set(["POST"]), icon: new Set(["PUT", "DELETE"]) };
export function parsePositiveInteger(value: string): number | null { if (!/^[1-9]\d*$/.test(value)) return null; const parsed = Number(value); return Number.isSafeInteger(parsed) ? parsed : null; }
export function parseChampionSlot(value: string): number | null { const parsed = parsePositiveInteger(value); return parsed != null && parsed <= 8 ? parsed : null; }
export function isChampionProxyAction(value: string): value is ChampionProxyAction { return Object.prototype.hasOwnProperty.call(ACTION_METHODS, value); }
export function isAllowedChampionMethod(action: ChampionProxyAction, method: string) { return ACTION_METHODS[action].has(method.toUpperCase()); }

export type ChampionMatchStage = "quarterfinal" | "semifinal" | "final";
export function parseChampionMatchStage(value: string): ChampionMatchStage | null {
  return value === "quarterfinal" || value === "semifinal" || value === "final" ? value : null;
}
export function parseChampionMatchSlot(stage: ChampionMatchStage, value: string): number | null {
  const slot = parsePositiveInteger(value);
  const maximum = stage === "quarterfinal" ? 4 : stage === "semifinal" ? 2 : 1;
  return slot != null && slot <= maximum ? slot : null;
}
