export const TOURNAMENT_RESULT_LABELS: Record<string, string> = {
  best64: "ベスト64",
  best32: "ベスト32",
  best16: "ベスト16",
  best8: "ベスト8",
  best4: "ベスト4",
  runner_up: "準優勝",
  champion: "優勝",
};

export const TOURNAMENT_RESULT_COLORS: Record<string, string> = {
  "優勝": "bg-amber-400/20 text-amber-300 ring-amber-400/50",
  "準優勝": "bg-slate-300/20 text-slate-200 ring-slate-300/50",
  "ベスト4": "bg-orange-500/20 text-orange-400 ring-orange-500/50",
  "ベスト8": "bg-blue-500/20 text-blue-400 ring-blue-500/50",
  "ベスト16": "bg-purple-500/20 text-purple-400 ring-purple-500/50",
  "ベスト32": "bg-slate-700/60 text-slate-400 ring-slate-600/50",
  "ベスト64": "bg-slate-800/60 text-slate-500 ring-slate-700/50",
};

export function tournamentResultLabel(result?: string | null) {
  if (!result) return null;
  return TOURNAMENT_RESULT_LABELS[result] ?? result;
}

export function tournamentResultClass(result?: string | null) {
  const label = tournamentResultLabel(result);
  return label
    ? TOURNAMENT_RESULT_COLORS[label] ?? "bg-slate-800/60 text-slate-500 ring-slate-700/50"
    : "bg-slate-800/60 text-slate-500 ring-slate-700/50";
}

const TRANSLATION_KEYS: Record<string, string> = {
  "優勝": "result.champion", champion: "result.champion",
  "準優勝": "result.runnerUp", runner_up: "result.runnerUp",
  "ベスト64": "result.best64", best64: "result.best64",
  "ベスト32": "result.best32", best32: "result.best32",
  "ベスト16": "result.best16", best16: "result.best16",
  "ベスト8": "result.best8", best8: "result.best8",
  "ベスト4": "result.semifinal", best4: "result.semifinal",
  FINAL: "result.final", "決勝": "result.final",
};

export function localizedTournamentResult(result: string | null | undefined, t: (key: string) => string) {
  if (!result) return null;
  return t(TRANSLATION_KEYS[result] ?? result);
}
