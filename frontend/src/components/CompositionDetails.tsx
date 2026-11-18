"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { teamMatchupPerspective } from "@/lib/teamMatchupPerspective";
import type { RegistrationScope } from "@/lib/tournaments";
import TeamDisplay from "./TeamDisplay";
import TeamMatchupHistory from "./TeamMatchupHistory";
import TeamPositionAnalysis from "./TeamPositionAnalysis";
import { CompositionBestResult, TeamRegistrationUsage, TeamStageFilter, TeamUsageCounts } from "./TeamStatisticsMeaning";

type Props = {
  tournamentId?: number;
  tournamentIds?: number[];
  playServer?: string;
  championshipId?: number;
  phase: string;
  canonicalId: string;
  onPhaseChange: (phase: string) => void;
  onTeamChange: (canonicalId: string) => void;
  allCharacters: any[];
  onSelectCharacter: (id: number) => void;
  registrationScopeByTournamentId: Record<number, RegistrationScope | undefined>;
  formal: boolean;
};

export default function CompositionDetails({
  tournamentId, tournamentIds, playServer, championshipId, phase, canonicalId, onPhaseChange,
  onTeamChange, allCharacters, onSelectCharacter, registrationScopeByTournamentId, formal,
}: Props) {
  const { t } = useI18n();
  const [response, setResponse] = useState<{ key: string; scope: string; data?: any; failed?: boolean }>();
  const [attempt, setAttempt] = useState(0);
  const [positionOpen, setPositionOpen] = useState(true);
  const scopeIds = tournamentIds?.join(",") ?? "";
  const selected = canonicalId.replaceAll("-", ",");
  const scopes = Object.values(registrationScopeByTournamentId);
  const eightOnly = scopes.length > 0 && scopes.every(scope => scope === "champion_8");
  const stages = eightOnly ? ["championship", "final"] : ["league", "championship", "final"];
  const normalizedPhase = phase === "initial" ? (eightOnly ? "championship" : "league")
    : phase === "best8" ? "championship" : phase;
  const stage = formal && stages.includes(normalizedPhase) ? normalizedPhase : "all";
  const query = new URLSearchParams({ registration_phase: stage, detail_team: selected }).toString();
  const scopeKey = JSON.stringify([tournamentId, scopeIds, playServer, championshipId]);
  const requestKey = JSON.stringify([scopeKey, query, attempt]);

  useEffect(() => {
    if (!tournamentId && !scopeIds) return;
    const controller = new AbortController();
    const scope = { tournament_ids: scopeIds.split(",").map(Number), play_server: playServer,
      championship_id: championshipId, registration_phase: stage, detail_team: selected };
    const url = tournamentId ? `/api/tournaments/${tournamentId}/dashboard/teams?${query}`
      : "/api/dashboard/cross-tournament/teams";
    const options = tournamentId ? {} : { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(scope) };
    fetch(url, { ...options, cache: "no-store", signal: controller.signal })
      .then(res => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      }).then(data => {
        if (!controller.signal.aborted) setResponse({ key: requestKey, scope: scopeKey, data });
      }).catch(() => {
        if (!controller.signal.aborted) setResponse({ key: requestKey, scope: scopeKey, failed: true });
      });
    return () => controller.abort();
  }, [tournamentId, scopeIds, playServer, championshipId, stage, selected, query, requestKey, scopeKey]);

  // Keep the selectors available while another phase or composition loads.
  const result = response?.key === requestKey ? response : undefined;
  const data = result?.data;
  const choices: { canonical_id: string; character_ids: number[] }[] = response?.scope === scopeKey ? response.data?.choices ?? [] : [];
  const characterNames = new Map(allCharacters.map(char => [char.id, char.name]));
  const selectedKey = data?.canonical_id ?? selected;
  const label = (ids: number[]) => ids.map(id => id === 9999 ? t("character.emptySlot") : characterNames.get(id) ?? String(id)).join(" / ");
  const team = data?.team;
  const defenseWins = team ? team.win_count - team.attack_wins : 0;
  const defenseRounds = team ? team.total_matches - team.attack_matches : 0;
  const perspective = teamMatchupPerspective(data?.matchups ?? [], selectedKey, value => String(value ?? ""));
  const winRate = (rate: number | null) => rate == null ? t("stats.noMatchRecords") : `${rate}%`;
  const sideRate = (wins: number, rounds: number) => winRate(rounds ? Math.round(wins / rounds * 1000) / 10 : null);

  return <div className="space-y-6">
    <div className="flex flex-wrap gap-3 rounded-xl bg-purple-500/10 p-4 ring-1 ring-purple-500/20">
      <select aria-label={t("stats.selectTeam")} className="min-w-0 flex-1 rounded-lg border border-slate-600 bg-slate-900 p-2 text-slate-100"
        value={selectedKey} onChange={event => onTeamChange(event.target.value)}>
        {!choices.some(row => row.canonical_id === selectedKey) && <option value={selectedKey}>
          {selectedKey ? label(selectedKey.split(",").map(Number)) : t("stats.selectTeam")}
        </option>}
        {choices.map(row => <option key={row.canonical_id} value={row.canonical_id}>{label(row.character_ids)}</option>)}
      </select>
      <TeamStageFilter stage={stage} onStageChange={onPhaseChange} formal={formal} stages={stages}/>
    </div>
    {!result && (tournamentId || scopeIds) ? <p role="status">{t("common.loading")}</p> : null}
    {result?.failed && <div role="alert">
      {t("error.matchHistory")}
      <button type="button" className="ml-3 underline" onClick={() => setAttempt(value => value + 1)}>{t("action.retry")}</button>
    </div>}
    {data && !team && <p className="text-slate-400">{t("stats.teamDataEmpty")}</p>}
    {team && <>
      <div className="flex flex-wrap items-center gap-6 rounded-xl bg-slate-800/50 p-4 ring-1 ring-white/10">
        <div className="grow">
          <TeamDisplay charIds={team.character_ids} allCharacters={allCharacters} onCharacterClick={onSelectCharacter}/>
          <TeamRegistrationUsage team={team}/>
          <p className="mt-2 text-sm text-slate-300"><TeamUsageCounts team={team}/></p>
        </div>
        <CompositionBestResult team={team}/>
        <div className="text-right">
          <p className="text-sm text-slate-400">{t("stats.overallWinRate")}</p>
          <p className="text-3xl font-black text-emerald-300">{winRate(team.win_rate)}</p>
          <p className="text-sm text-slate-400">{t("stats.winsLosses", { wins: team.win_count, losses: team.total_matches - team.win_count })}</p>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col items-center justify-center rounded-2xl bg-blue-500/10 p-6 text-center ring-1 ring-blue-500/20">
          <p className="mb-2 text-sm text-blue-400">{t("stats.attackWinRate")}</p>
          <p className="text-4xl font-black text-blue-400">{sideRate(team.attack_wins, team.attack_matches)}</p>
          <p className="mt-2 text-sm text-blue-300">
            {t("stats.winsLosses", { wins: team.attack_wins, losses: team.attack_matches - team.attack_wins })}
          </p>
        </div>
        <div className="flex flex-col items-center justify-center rounded-2xl bg-red-500/10 p-6 text-center ring-1 ring-red-500/20">
          <p className="mb-2 text-sm text-red-400">{t("stats.defenseWinRate")}</p>
          <p className="text-4xl font-black text-red-400">
            {sideRate(defenseWins, defenseRounds)}
          </p>
          <p className="mt-2 text-sm text-red-300">
            {t("stats.winsLosses", { wins: defenseWins, losses: defenseRounds - defenseWins })}
          </p>
        </div>
      </div>
      <TeamPositionAnalysis positionStats={team.position_stats} open={positionOpen} onToggle={() => setPositionOpen(value => !value)}/>
    </>}
    {perspective.details.length > 0 && <TeamMatchupHistory key={`${selectedKey}:${stage}`}
      groupByOpponent matchupDetails={perspective.details} allCharacters={allCharacters}
      onSelectCharacter={onSelectCharacter} onSelectOpponent={onTeamChange}
      registrationScopeByTournamentId={registrationScopeByTournamentId}/>}
  </div>;
}
