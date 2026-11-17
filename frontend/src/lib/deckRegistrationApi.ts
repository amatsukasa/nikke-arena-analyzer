import { RegistrationTeam, normalizeAnalyzedRegistrationTeams, registrationTeamsPayload } from "./deckRegistration";
import { apiErrorMessage } from "./tournaments";

type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;
export type RegistrationAnalysisTarget =
  | { format: "full_64"; tournamentId: number; seedNumber: number }
  | { format: "champion_8"; tournamentId: number; playerId: number };

// Keep endpoint selection and its multipart contract together. champion_8 allows
// only five crop flags; its player and tournament are already in the URL.
export function registrationAnalysisRequest(target: RegistrationAnalysisTarget, files: {file: File; preCropped: boolean}[]) {
  const body = new FormData();
  files.forEach(({file, preCropped}) => {
    body.append("images", file);
    body.append("image_pre_cropped", String(preCropped));
  });
  if (target.format === "full_64") {
    body.append("tournament_id", String(target.tournamentId));
    body.append("seed_number", String(target.seedNumber));
  }
  const url = target.format === "champion_8"
    ? `/api/tournaments/${target.tournamentId}/players/by-id/${target.playerId}/analyze-deck`
    : "/api/analyze/deck";
  return {url, body};
}

async function registrationResponse(response: Response, fallback: string) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(apiErrorMessage(data, fallback));
  return data;
}

export async function analyzeRegistrationDecks(target: RegistrationAnalysisTarget, files: {file: File; preCropped: boolean}[], fetcher: Fetcher = fetch) {
  const {url, body} = registrationAnalysisRequest(target, files);
  return normalizeAnalyzedRegistrationTeams(await registrationResponse(await fetcher(url, {method: "POST", body}), "画像解析に失敗しました。"));
}

// Callers retain their own eligibility/version context and post-save refresh.
// Only serialization, transport and API error handling are shared here.
export async function saveRegistrationDecks(url: string, method: "POST" | "PUT", teams: RegistrationTeam[], context: Record<string, unknown> = {}, fetcher: Fetcher = fetch) {
  return registrationResponse(await fetcher(url, {
    method, headers: {"Content-Type": "application/json"},
    body: JSON.stringify({...context, teams: registrationTeamsPayload(teams)}),
  }), "編成を保存できませんでした。");
}
