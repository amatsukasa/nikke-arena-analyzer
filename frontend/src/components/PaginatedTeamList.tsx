"use client";
import { useState, useEffect } from "react";
import TeamDisplay from "./TeamDisplay";

interface PaginatedTeamListProps {
  tournamentIds?: number[];
  tournamentId?: number;
  mode?: "single" | "cross";
  playServer?: string;
  championshipId?: number;
  allCharacters: any[];
  characterIds?: number[];
  sortBy?: "count" | "win_rate";
  sortOrder?: "desc" | "asc";
  minMatches?: number;
  minUsage?: number;
  minWinRate?: number;
  bestResult?: string;
  onTeamClick: (canonicalId: string) => void;
  selectedTeam?: string;
}

export default function PaginatedTeamList({
  tournamentIds = [],
  tournamentId,
  mode,
  playServer,
  championshipId,
  allCharacters,
  characterIds = [],
  sortBy = "count",
  sortOrder = "desc",
  minMatches = 0,
  minUsage = 0,
  minWinRate = 0,
  bestResult = "",
  onTeamClick,
  selectedTeam
}: PaginatedTeamListProps) {

  const [teams, setTeams] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const limit = 10;

  const fetchTeams = async (currentOffset: number, reset: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
      const authHeaders: any = token ? { "Authorization": `Bearer ${token}` } : {};

      const isSingle = mode === "single" || (mode !== "cross" && tournamentId !== undefined);
      const targetId = tournamentId !== undefined ? tournamentId : tournamentIds[0];
      let res;
      if (isSingle && targetId) {
        let url = `/api/tournaments/${targetId}/dashboard/teams?limit=${limit}&offset=${currentOffset}&sort_by=${sortBy}&sort_order=${sortOrder}`;
        if (characterIds.length > 0) {
          url += `&character_ids=${characterIds.join(",")}`;
        }
        if (minMatches > 0) url += `&min_matches=${minMatches}`;
        if (minUsage > 0) url += `&min_usage=${minUsage}`;
        if (minWinRate > 0) url += `&min_win_rate=${minWinRate}`;
        if (bestResult) url += `&best_result=${encodeURIComponent(bestResult)}`;
        res = await fetch(url, { headers: authHeaders });
      } else {
        res = await fetch(`/api/dashboard/cross-tournament/teams`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify({
            tournament_ids: tournamentIds,
            play_server: playServer,
            championship_id: championshipId,
            limit,
            offset: currentOffset,
            character_ids: characterIds.length > 0 ? characterIds : undefined,
            sort_by: sortBy,
            sort_order: sortOrder,
            min_matches: minMatches,
            min_usage: minUsage,
            min_win_rate: minWinRate,
            best_result: bestResult || undefined
          })
        });
      }
      
      if (!res.ok) {
        console.error("API error in PaginatedTeamList:", res.status);
        if (res.status === 401) {
          setError("データを取得できませんでした（認証が必要です）");
        } else {
          setError("データを取得できませんでした");
        }
        if (reset) setTeams([]);
        setTotal(0);
        setHasMore(false);
        return;
      }

      const data = await res.json();
      const newTeams = Array.isArray(data.teams) ? data.teams : [];
      if (reset) {
        setTeams(newTeams);
      } else {
        setTeams(prev => [...prev, ...newTeams]);
      }
      setTotal(data.total || 0);
      setHasMore(currentOffset + newTeams.length < (data.total || 0));
    } catch (e) {
      console.error("Failed to fetch teams", e);
      setError("データを取得できませんでした");
    } finally {
      setLoading(false);
    }
  };

  // Reset and fetch when dependencies change
  useEffect(() => {
    if (tournamentIds.length === 0) return;
    setTeams([]);
    setOffset(0);
    setHasMore(true);
    fetchTeams(0, true);
  }, [tournamentIds.join(","), characterIds.join(","), sortBy, sortOrder, minMatches, minUsage, minWinRate, bestResult]);

  const handleLoadMore = () => {
    if (loading || !hasMore) return;
    const nextOffset = offset + limit;
    setOffset(nextOffset);
    fetchTeams(nextOffset, false);
  };

  if (teams.length === 0 && !loading) {
    return (
      <div className="text-center py-12 bg-slate-800/30 rounded-2xl ring-1 ring-white/5">
        <p className="text-slate-400 text-lg">{error || "該当する編成はありません"}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        {teams.map((team: any, idx: number) => {
          const resultColors: Record<string, string> = {
            "優勝":   "bg-amber-400/20 text-amber-300 ring-amber-400/50",
            "準優勝": "bg-slate-300/20 text-slate-200 ring-slate-300/50",
            "ベスト4":  "bg-orange-500/20 text-orange-400 ring-orange-500/50",
            "ベスト8":  "bg-blue-500/20 text-blue-400 ring-blue-500/50",
            "ベスト16": "bg-purple-500/20 text-purple-400 ring-purple-500/50",
            "ベスト32": "bg-slate-700/60 text-slate-400 ring-slate-600/50",
            "ベスト64": "bg-slate-800/60 text-slate-500 ring-slate-700/50",
          };
          const resultColor = resultColors[team.best_result] ?? "bg-slate-700/40 text-slate-400 ring-slate-600/40";

          return (
            <div
              key={`${team.canonical_id}-${idx}`}
              onClick={() => onTeamClick(team.canonical_id)}
              className={`flex items-center gap-3 bg-slate-800/50 hover:bg-slate-700/60 cursor-pointer transition-colors p-4 rounded-xl ring-1 ${selectedTeam === team.canonical_id ? "ring-emerald-500 bg-slate-700/80" : "ring-white/5"}`}
            >
              {/* 順位番号 */}
              <div className="text-slate-500 font-bold text-sm w-6 text-center shrink-0">
                {idx + 1}
              </div>

              {/* キャラ画像 */}
              <div className="flex-1 min-w-0">
                <TeamDisplay charIds={team.character_ids} allCharacters={allCharacters} />
              </div>

              {/* 中央：最終成績 / 採用数 / 対戦数 */}
              <div className="flex flex-col items-end gap-1 shrink-0 text-right">
                {team.best_result && (
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ring-1 ${resultColor}`}>
                    {team.best_result}
                  </span>
                )}
                <span className="text-xs text-slate-400">
                  採用 <span className="text-slate-200 font-semibold">{team.count}</span> 回
                </span>
                <span className="text-xs text-slate-400">
                  対戦 <span className="text-slate-200 font-semibold">{team.total_matches ?? "-"}</span> 回
                </span>
              </div>

              {/* 右端：勝率を大きく強調 */}
              <div className={`px-4 py-1.5 rounded-lg font-black text-lg min-w-[90px] text-center shrink-0 ${
                team.win_rate >= 50 ? "bg-emerald-400/10 text-emerald-400" : "bg-amber-400/10 text-amber-400"
              }`}>
                {team.win_rate}%
              </div>
            </div>
          );
        })}
      </div>

      {hasMore && (
        <button
          onClick={handleLoadMore}
          disabled={loading}
          className="w-full py-4 bg-slate-800/80 hover:bg-slate-700 text-slate-300 font-bold rounded-xl ring-1 ring-white/10 transition-colors disabled:opacity-50"
        >
          {loading ? "読み込み中..." : "もっと見る"}
        </button>
      )}
    </div>
  );
}
