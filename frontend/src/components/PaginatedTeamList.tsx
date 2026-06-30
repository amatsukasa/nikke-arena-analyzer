"use client";
import { useState, useEffect } from "react";
import TeamDisplay from "./TeamDisplay";

interface PaginatedTeamListProps {
  tournamentIds: number[];
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
  tournamentIds,
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

  const limit = 10;

  const fetchTeams = async (currentOffset: number, reset: boolean) => {
    setLoading(true);
    try {
      let res;
      if (tournamentIds.length === 1) {
        let url = `/api/tournaments/${tournamentIds[0]}/dashboard/teams?limit=${limit}&offset=${currentOffset}&sort_by=${sortBy}&sort_order=${sortOrder}`;
        if (characterIds.length > 0) {
          url += `&character_ids=${characterIds.join(",")}`;
        }
        if (minMatches > 0) url += `&min_matches=${minMatches}`;
        if (minUsage > 0) url += `&min_usage=${minUsage}`;
        if (minWinRate > 0) url += `&min_win_rate=${minWinRate}`;
        if (bestResult) url += `&best_result=${encodeURIComponent(bestResult)}`;
        res = await fetch(url);
      } else {
        res = await fetch("/api/dashboard/cross-tournament/teams", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            tournament_ids: tournamentIds,
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
      
      const data = await res.json();
      
      if (reset) {
        setTeams(data.teams);
      } else {
        setTeams(prev => [...prev, ...data.teams]);
      }
      setTotal(data.total);
      setHasMore(currentOffset + data.teams.length < data.total);
    } catch (e) {
      console.error("Failed to fetch teams", e);
    } finally {
      setLoading(false);
    }
  };

  // Reset and fetch when dependencies change
  useEffect(() => {
    if (tournamentIds.length === 0) return;
    setOffset(0);
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
        <p className="text-slate-400 text-lg">該当する編成はありません</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        {teams.map((team: any, idx: number) => (
          <div 
            key={`${team.canonical_id}-${idx}`} 
            onClick={() => onTeamClick(team.canonical_id)} 
            className={`flex items-center justify-between bg-slate-800/50 hover:bg-slate-700/60 cursor-pointer transition-colors p-4 rounded-xl ring-1 ${selectedTeam === team.canonical_id ? 'ring-emerald-500 bg-slate-700/80' : 'ring-white/5'}`}
          >
            <TeamDisplay charIds={team.character_ids} allCharacters={allCharacters} />
            <div className="text-right flex items-center justify-end gap-3">
              <div className="text-emerald-400 font-bold bg-emerald-400/10 px-3 py-1 rounded-lg">
                {team.count} 回採用
              </div>
              <div className="text-sm text-slate-400 hidden sm:block">
                勝率: {team.win_rate}% ({team.win_count}/{team.total_matches})
              </div>
            </div>
          </div>
        ))}
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
