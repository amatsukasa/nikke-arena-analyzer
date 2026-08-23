export type MatchSide = "left" | "right";
export type MatchStage = "quarterfinal" | "semifinal" | "final";

export interface MatchEditorPlayer {
  id: number;
  name: string;
  detail?: string;
  iconUrl?: string | null;
}

export interface MatchEditorRound {
  roundNumber: number;
  winner: MatchSide | null;
}

export interface MatchEditorResult {
  rounds: MatchEditorRound[];
  issues: string[];
}

export const CHAMPION_MATCH_ORDER: ReadonlyArray<readonly [MatchStage, number]> = [
  ["quarterfinal", 1], ["quarterfinal", 2], ["quarterfinal", 3], ["quarterfinal", 4],
  ["semifinal", 1], ["semifinal", 2], ["final", 1],
];

export function parseChampionMatchStage(value: string): MatchStage | null {
  return value === "quarterfinal" || value === "semifinal" || value === "final" ? value : null;
}

export function validChampionMatchSlot(stage: MatchStage, slot: number) {
  return Number.isInteger(slot) && slot >= 1 && slot <= (stage === "quarterfinal" ? 4 : stage === "semifinal" ? 2 : 1);
}

export function majoritySide(rounds: MatchEditorRound[]): MatchSide | null {
  if (rounds.length !== 5 || rounds.some(round => round.winner !== "left" && round.winner !== "right")) return null;
  return rounds.filter(round => round.winner === "left").length >= 3 ? "left" : "right";
}

export function validateMatchEditorResult(result: MatchEditorResult | null) {
  if (!result) return ["解析結果がありません。"];
  const numbers = result.rounds.map(round => round.roundNumber).sort((a, b) => a - b);
  const issues = [...result.issues];
  if (numbers.join(",") !== "1,2,3,4,5") issues.push("ラウンド1～5をすべて確認してください。");
  if (result.rounds.some(round => round.winner !== "left" && round.winner !== "right")) issues.push("未判定のラウンドを修正してください。");
  return Array.from(new Set(issues));
}

export function championDependentLabels(stage: MatchStage, slot: number) {
  if (stage === "quarterfinal") return [`SF${slot <= 2 ? 1 : 2}`, "Final"];
  if (stage === "semifinal") return ["Final"];
  return [];
}

export function normalizeChampionMatchAnalysis(data:any,attackerId:number,defenderId:number):MatchEditorResult {
  return {rounds:(Array.isArray(data?.round_results)?data.round_results:[]).map((round:any)=>({roundNumber:round.round_number,winner:round.side==="left"||round.winner_id===attackerId?"left":round.side==="right"||round.winner_id===defenderId?"right":null})),issues:Array.isArray(data?.issues)?data.issues:[]};
}

export function championMatchPayload(result:MatchEditorResult,attackerId:number,defenderId:number){
  const issues=validateMatchEditorResult(result);const winner=majoritySide(result.rounds);if(issues.length||winner==null)throw new Error(issues[0]||"勝者を確定できません。");
  return {winner_id:winner==="left"?attackerId:defenderId,round_results:[...result.rounds].sort((a,b)=>a.roundNumber-b.roundNumber).map(round=>({round_number:round.roundNumber,winner_id:round.winner==="left"?attackerId:defenderId}))};
}

export function normalizeFull64MatchAnalysis(data:any):MatchEditorResult {
  return {rounds:(Array.isArray(data?.rounds)?data.rounds:[]).map((round:any)=>({roundNumber:round.round,winner:round.left==="WIN"?"left":round.right==="WIN"?"right":null})),issues:[]};
}

export function full64MatchPayload(result:MatchEditorResult,tournamentId:number,stage:string,attackerSeed:number,defenderSeed:number){
  const issues=validateMatchEditorResult(result);const winner=majoritySide(result.rounds);if(issues.length||winner==null)throw new Error(issues[0]||"勝者を確定できません。");
  return {tournament_id:tournamentId,stage,attacker_seed:attackerSeed,defender_seed:defenderSeed,winner,rounds:[...result.rounds].sort((a,b)=>a.roundNumber-b.roundNumber).map(round=>({round:round.roundNumber,left:round.winner==="left"?"WIN":"LOSE",right:round.winner==="right"?"WIN":"LOSE"}))};
}
