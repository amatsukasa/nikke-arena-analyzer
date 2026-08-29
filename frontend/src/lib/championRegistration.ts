export type ChampionTeamStatus = "not_saved" | "incomplete" | "complete" | "load_failed";

export interface ChampionPlayer {
  id: number;
  tournament_id: number;
  champion_slot: number;
  seed_number: number | null;
  name: string;
  icon_url: string | null;
}

import {
  RegistrationTeam,
  normalizeAnalyzedRegistrationTeams,
  normalizeSavedRegistrationTeams,
  registrationSaveConfirmation,
  registrationTeamsPayload,
  validateRegistrationTeams,
} from "./deckRegistration";

export type ChampionTeam = RegistrationTeam;

export interface ChampionSlotState {
  champion_slot: number;
  player: ChampionPlayer | null;
  teamStatus: ChampionTeamStatus;
  teams: ChampionTeam[];
  error?: string;
}

export const CHAMPION_SLOT_PAIRS = [[1, 2], [3, 4], [5, 6], [7, 8]] as const;

export const championPlayerUrl = (tournamentId: number, playerId: number) =>
  `/api/tournaments/${tournamentId}/players/by-id/${playerId}`;
export const championTeamsUrl = (tournamentId: number, playerId: number) =>
  `${championPlayerUrl(tournamentId, playerId)}/teams`;
export const championAnalyzeUrl = (tournamentId: number, playerId: number) =>
  `${championPlayerUrl(tournamentId, playerId)}/analyze-deck`;
export const championIconUrl = (tournamentId: number, playerId: number) =>
  `${championPlayerUrl(tournamentId, playerId)}/icon`;

export function championProgress(slots: ChampionSlotState[]) {
  return {
    players: slots.filter(slot => slot.player).length,
    complete: slots.filter(slot => slot.teamStatus === "complete").length,
  };
}

export function visibleChampionStatus(slot: ChampionSlotState, hasUnsavedAnalysis: boolean) {
  if (hasUnsavedAnalysis) return "画像解析済み・確認待ち";
  if (!slot.player || slot.teamStatus === "not_saved") return "未登録";
  if (slot.teamStatus === "complete") return "登録完了";
  return "修正が必要";
}

export function validateChampionTeams(teams: ChampionTeam[], knownCharacterIds: Set<number>) {
  return validateRegistrationTeams(teams, knownCharacterIds);
}

export function normalizeSavedTeams(data: any): ChampionTeam[] {
  return normalizeSavedRegistrationTeams(data);
}

export function normalizeAnalyzedTeams(data: any): ChampionTeam[] {
  return normalizeAnalyzedRegistrationTeams(data);
}

export function championTeamsPayload(teams: ChampionTeam[]) {
  return { teams: registrationTeamsPayload(teams) };
}

export function championSaveConfirmation(
  playerName: string,
  championSlot: number,
  seedNumber: number | null,
  teams: ChampionTeam[],
  characterNames: Map<number, string>,
  overwrite: boolean,
) {
  const seed = seedNumber == null ? "不明" : String(seedNumber);
  return registrationSaveConfirmation(playerName, `対抗戦枠${championSlot}・元シード${seed}`, teams, characterNames, overwrite);
}
