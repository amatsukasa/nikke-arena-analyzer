"use client";

import { useMemo, useState } from "react";
import TeamDisplay from "./TeamDisplay";

type MatchupFilterResult = "ALL" | "WIN" | "LOSE";
type MatchupFilterSide = "ALL" | "ATTACK" | "DEFENSE";

type Props = {
  matchupDetails: any[];
  allCharacters: any[];
  onSelectCharacter: (characterId: number) => void;
  onSelectOpponent: (canonicalId: string, team?: any) => void;
};

const STAGE_ORDER = [
  "決勝", "FINAL",
  "準決勝", "Best 4", "ベスト4",
  "Best 8", "ベスト8",
  "Best 16", "ベスト16",
  "Best 32", "ベスト32",
  "Best 64", "ベスト64",
  "不明",
];

export default function TeamMatchupHistory({
  matchupDetails,
  allCharacters,
  onSelectCharacter,
  onSelectOpponent,
}: Props) {
  const [resultFilter, setResultFilter] = useState<MatchupFilterResult>("ALL");
  const [sideFilter, setSideFilter] = useState<MatchupFilterSide>("ALL");
  const [stageFilter, setStageFilter] = useState("ALL");

  const availableStages = useMemo(
    () => Array.from(new Set(matchupDetails.map((match) => match.stage || "不明")))
      .sort((a, b) => {
        const indexA = STAGE_ORDER.indexOf(a);
        const indexB = STAGE_ORDER.indexOf(b);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return a.localeCompare(b);
      }),
    [matchupDetails],
  );

  const filteredMatchups = matchupDetails.filter((match) => {
    if (resultFilter === "WIN" && !match.isWin) return false;
    if (resultFilter === "LOSE" && match.isWin) return false;
    if (sideFilter === "ATTACK" && !match.isAttacker) return false;
    if (sideFilter === "DEFENSE" && match.isAttacker) return false;
    if (stageFilter !== "ALL" && (match.stage || "不明") !== stageFilter) return false;
    return true;
  });

  const resultBadge = (isWin: boolean) => (
    <span className={`rounded-md px-2.5 py-1 text-sm font-black tracking-wide ring-1 ${
      isWin
        ? "bg-emerald-500/20 text-emerald-300 ring-emerald-500/40"
        : "bg-red-500/15 text-red-300 ring-red-500/30"
    }`}>
      {isWin ? "WIN" : "LOSE"}
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
          {filteredMatchups.map((match, index) => (
            <div
              key={`${match.tournamentName ?? ""}-${match.stage ?? ""}-${index}`}
              onClick={() => onSelectOpponent(match.opponentCanonical, {
                character_ids: match.opponent,
                canonical_id: match.opponentCanonical,
              })}
              className="cursor-pointer space-y-2 rounded-xl bg-slate-800/30 p-4 ring-1 ring-white/5 transition-colors hover:bg-slate-700/50"
            >
              <div className="flex items-center space-x-2 text-xs">
                <span className="whitespace-nowrap rounded bg-indigo-500/10 px-2 py-0.5 font-bold text-indigo-400 ring-1 ring-indigo-500/20">
                  {match.tournamentName || "不明"}
                </span>
                <span className="text-slate-400">
                  {match.attackerName} <span className="text-slate-600">vs</span> {match.defenderName}
                </span>
              </div>

              <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                <div className={`rounded px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ring-1 ${
                  match.stage === "決勝"
                    ? "bg-amber-500/20 text-amber-400 ring-amber-500/30"
                    : match.stage?.includes("準決勝")
                      ? "bg-orange-500/20 text-orange-400 ring-orange-500/30"
                      : "bg-slate-700/50 text-slate-400 ring-slate-600/50"
                }`}>
                  {match.stage || "不明"}
                </div>

                <div className="flex min-w-0 flex-1 flex-col items-center gap-3 sm:flex-row sm:justify-center">
                  <div className={`rounded-xl p-2 ring-1 ${
                    !match.isAttacker
                      ? "bg-purple-500/10 ring-purple-500/40"
                      : "ring-white/5"
                  }`}>
                    <div className="mb-2 flex flex-wrap items-center justify-center gap-2">
                      <span className="rounded bg-blue-500/20 px-2 py-0.5 text-[10px] font-bold text-blue-400">攻撃側</span>
                      {match.isAttacker && <span className="text-[10px] font-bold text-purple-300">検索対象</span>}
                      {match.isAttacker && resultBadge(match.isWin)}
                    </div>
                    <TeamDisplay
                      charIds={match.attackerTeam}
                      allCharacters={allCharacters}
                      collectionLevels={match.attackerCollections}
                      onCharacterClick={onSelectCharacter}
                    />
                  </div>

                  <div className="shrink-0 text-sm font-black text-slate-500">VS</div>

                  <div className={`rounded-xl p-2 ring-1 ${
                    match.isAttacker
                      ? "bg-purple-500/10 ring-purple-500/40"
                      : "ring-white/5"
                  }`}>
                    <div className="mb-2 flex flex-wrap items-center justify-center gap-2">
                      <span className="rounded bg-red-500/20 px-2 py-0.5 text-[10px] font-bold text-red-400">防衛側</span>
                      {!match.isAttacker && <span className="text-[10px] font-bold text-purple-300">検索対象</span>}
                      {!match.isAttacker && resultBadge(match.isWin)}
                    </div>
                    <TeamDisplay
                      charIds={match.defenderTeam}
                      allCharacters={allCharacters}
                      collectionLevels={match.defenderCollections}
                      onCharacterClick={onSelectCharacter}
                    />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-xl bg-slate-800/30 p-8 text-center text-slate-400 ring-1 ring-white/5">
          条件に一致する対戦履歴がありません
        </div>
      )}
    </div>
  );
}
