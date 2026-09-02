"use client";

import { useMemo, useState } from "react";
import TeamDisplay from "./TeamDisplay";
import { formatMatchStageForDisplay, sortUniqueMatchStageDisplays } from "@/lib/matchStageDisplay";
import { matchupSideResults, type MatchupResult } from "@/lib/teamMatchupPerspective";
import type { RegistrationScope } from "@/lib/tournaments";
import { tournamentResultClass } from "@/lib/tournamentResult";

type MatchupFilterResult = "ALL" | "WIN" | "LOSE";
type MatchupFilterSide = "ALL" | "ATTACK" | "DEFENSE";

type Props = {
  matchupDetails: any[];
  allCharacters: any[];
  onSelectCharacter: (characterId: number) => void;
  onSelectOpponent: (canonicalId: string, team?: any) => void;
  registrationScope?: RegistrationScope | null;
  registrationScopeByTournamentId?: Record<number, RegistrationScope | undefined>;
};

export function MatchStageBadge({ stage }: { stage?: string | null }) {
  const label = stage || "不明";
  const colorClass = label === "FINAL"
    ? "bg-amber-400/20 text-amber-300 ring-amber-400/50"
    : tournamentResultClass(label);
  return (
    <div className={`self-start rounded px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ring-1 ${colorClass}`}>
      {label}
    </div>
  );
}

export default function TeamMatchupHistory({
  matchupDetails,
  allCharacters,
  onSelectCharacter,
  onSelectOpponent,
  registrationScope,
  registrationScopeByTournamentId,
}: Props) {
  const [resultFilter, setResultFilter] = useState<MatchupFilterResult>("ALL");
  const [sideFilter, setSideFilter] = useState<MatchupFilterSide>("ALL");
  const [stageFilter, setStageFilter] = useState("ALL");

  const displayMatchups = useMemo(
    () => matchupDetails.map((match) => ({
      ...match,
      displayStage: formatMatchStageForDisplay({
        registrationScope: registrationScope
          ?? registrationScopeByTournamentId?.[Number(match.tournament_id)],
        rawStage: match.stage,
        bracketStage: match.bracket_stage,
        bracketSlot: match.bracket_slot,
      }),
    })),
    [matchupDetails, registrationScope, registrationScopeByTournamentId],
  );

  const availableStages = useMemo(
    () => sortUniqueMatchStageDisplays(displayMatchups.map((match) => match.displayStage)),
    [displayMatchups],
  );

  const filteredMatchups = displayMatchups.filter((match) => {
    if (resultFilter === "WIN" && !match.isWin) return false;
    if (resultFilter === "LOSE" && match.isWin) return false;
    if (sideFilter === "ATTACK" && !match.isAttacker) return false;
    if (sideFilter === "DEFENSE" && match.isAttacker) return false;
    if (stageFilter !== "ALL" && (match.displayStage || "不明") !== stageFilter) return false;
    return true;
  });

  const resultBadge = (result: MatchupResult, emphasized: boolean, sideLabel: string) => (
    <span
      aria-label={`${sideLabel}結果: ${result}${emphasized ? "（分析対象）" : ""}`}
      className={`shrink-0 rounded-md tracking-wider ring-1 ${
        emphasized
          ? "px-1 py-2 text-center text-sm font-black xl:min-w-16 xl:px-3 xl:text-lg"
          : "px-1 py-1 text-[10px] font-bold opacity-70 xl:px-2 xl:text-xs"
      } ${
        result === "WIN"
          ? "bg-emerald-500/20 text-emerald-300 ring-emerald-500/40"
          : "bg-red-500/15 text-red-300 ring-red-500/30"
      }`}>
      {result}
    </span>
  );

  return (
    <div className="mt-8 space-y-4">
      <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <h3 className="font-bold text-white">この編成の対戦履歴</h3>
        <div className="flex flex-wrap gap-2">
          <select
            className="rounded-lg border border-white/10 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-purple-500"
            value={resultFilter}
            onChange={(event) => setResultFilter(event.target.value as MatchupFilterResult)}
          >
            <option value="ALL">勝敗：すべて</option>
            <option value="WIN">WIN</option>
            <option value="LOSE">LOSE</option>
          </select>
          <select
            className="rounded-lg border border-white/10 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-purple-500"
            value={sideFilter}
            onChange={(event) => setSideFilter(event.target.value as MatchupFilterSide)}
          >
            <option value="ALL">攻防：すべて</option>
            <option value="ATTACK">攻撃</option>
            <option value="DEFENSE">防衛</option>
          </select>
          <select
            className="rounded-lg border border-white/10 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-purple-500"
            value={stageFilter}
            onChange={(event) => setStageFilter(event.target.value)}
          >
            <option value="ALL">ラウンド：すべて</option>
            {availableStages.map((stage) => (
              <option key={stage} value={stage}>{stage}</option>
            ))}
          </select>
        </div>
      </div>

      {filteredMatchups.length > 0 ? (
        <div className="space-y-2">
          {filteredMatchups.map((match, index) => {
            const sideResults = matchupSideResults(match);
            return (
              <div
                key={match.participationKey || `${match.tournamentName ?? ""}-${match.stage ?? ""}-${index}`}
                onClick={() => onSelectOpponent(match.opponentCanonical, {
                  character_ids: match.opponent,
                  canonical_id: match.opponentCanonical,
                })}
                className="cursor-pointer space-y-2 rounded-xl bg-slate-800/30 p-1 ring-1 ring-white/5 transition-colors hover:bg-slate-700/50 sm:p-4"
              >
                <div className="flex min-w-0 items-center space-x-2 text-xs">
                  <span className="shrink-0 whitespace-nowrap rounded bg-indigo-500/10 px-2 py-0.5 font-bold text-indigo-400 ring-1 ring-indigo-500/20">
                    {match.tournamentName || "不明"}
                  </span>
                  <span className="min-w-0 truncate text-slate-400">
                    {match.attackerName} <span className="text-slate-600">vs</span> {match.defenderName}
                  </span>
                </div>

              <div className="flex min-w-0 flex-col gap-4 xl:flex-row xl:items-center">
                <MatchStageBadge stage={match.displayStage} />

                <div className="grid min-w-0 flex-1 grid-cols-[2.5rem_auto] items-center justify-center gap-x-1 gap-y-3 xl:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] xl:justify-stretch xl:gap-3">
                  <div className="contents xl:col-start-1 xl:row-start-1 xl:flex xl:min-w-0 xl:items-center xl:justify-center xl:gap-2">
                    <div className="col-start-1 row-start-1 justify-self-center xl:block">
                      {resultBadge(sideResults.attacker, match.isAttacker, "攻撃側")}
                    </div>
                    <div
                      data-matchup-side="attacker"
                      className={`col-start-2 row-start-1 w-fit max-w-full min-w-0 justify-self-center rounded-xl p-1 sm:p-2 xl:col-start-auto xl:row-start-auto xl:justify-self-auto ${match.isAttacker ? "bg-purple-500/10 ring-2 ring-purple-400/60" : "ring-1 ring-white/5"}`}
                    >
                      <div className="mb-2 flex items-center justify-center gap-2">
                        <span className="rounded bg-blue-500/20 px-2 py-0.5 text-[10px] font-bold text-blue-400">攻撃側</span>
                        {match.isAttacker && <span className="rounded bg-purple-500/20 px-2 py-0.5 text-[10px] font-black text-purple-200 ring-1 ring-purple-400/40">分析対象</span>}
                      </div>
                      <div data-matchup-characters="attacker" className="flex min-w-0 justify-center [&>div]:justify-center">
                        <TeamDisplay
                          charIds={match.attackerTeam}
                          allCharacters={allCharacters}
                          collectionLevels={match.attackerCollections}
                          onCharacterClick={onSelectCharacter}
                        />
                      </div>
                    </div>

                  </div>

                  <div className="col-start-2 row-start-2 shrink-0 text-center text-sm font-black text-slate-500 xl:col-start-2 xl:row-start-1">VS</div>

                  <div className="contents xl:col-start-3 xl:row-start-1 xl:flex xl:min-w-0 xl:items-center xl:justify-center xl:gap-2">
                    <div
                      data-matchup-side="defender"
                      className={`col-start-2 row-start-3 w-fit max-w-full min-w-0 justify-self-center rounded-xl p-1 sm:p-2 xl:col-start-auto xl:row-start-auto xl:justify-self-auto ${!match.isAttacker ? "bg-purple-500/10 ring-2 ring-purple-400/60" : "ring-1 ring-white/5"}`}
                    >
                      <div className="mb-2 flex items-center justify-center gap-2">
                        <span className="rounded bg-red-500/20 px-2 py-0.5 text-[10px] font-bold text-red-400">防衛側</span>
                        {!match.isAttacker && <span className="rounded bg-purple-500/20 px-2 py-0.5 text-[10px] font-black text-purple-200 ring-1 ring-purple-400/40">分析対象</span>}
                      </div>
                      <div data-matchup-characters="defender" className="flex min-w-0 justify-center [&>div]:justify-center">
                        <TeamDisplay
                          charIds={match.defenderTeam}
                          allCharacters={allCharacters}
                          collectionLevels={match.defenderCollections}
                          onCharacterClick={onSelectCharacter}
                        />
                      </div>
                    </div>
                    <div className="col-start-1 row-start-3 justify-self-center xl:block">
                      {resultBadge(sideResults.defender, !match.isAttacker, "防衛側")}
                    </div>
                  </div>
                </div>
              </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl bg-slate-800/30 p-8 text-center text-slate-400 ring-1 ring-white/5">
          条件に一致する対戦履歴がありません
        </div>
      )}
    </div>
  );
}
