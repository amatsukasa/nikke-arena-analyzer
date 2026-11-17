"use client";
import { CompositionBestResult, RegistrationPhaseLabel } from "@/components/TeamStatisticsMeaning";
import { useState, useEffect, useRef } from "react";
import TeamDisplay from "./TeamDisplay";
import { useI18n } from "@/i18n/I18nProvider";
import { localizedTournamentResult } from "@/lib/tournamentResult";

interface PaginatedTeamListProps {
  tournamentIds?: number[];
  tournamentId?: number;
  mode?: "single" | "cross";
  registrationPhase?: string;
  playServer?: string;
  championshipId?: number;
  allCharacters: any[];
  characterIds?: number[];
  excludedCharacterIds?: number[];
  sortBy?: "count" | "win_rate" | "composition_best_result";
  sortOrder?: "desc" | "asc";
  minMatches?: number;
  minUsage?: number;
  minWinRate?: number;
  bestResult?: string;
  compositionBestResult?: string;
  commanderBestResult?: string;
  onTeamClick: (canonicalId: string, teamObj?: any) => void;
  selectedTeam?: string;
}

export default function PaginatedTeamList({
  tournamentIds = [],
  tournamentId,
  mode,
  registrationPhase="initial",
  playServer,
  championshipId,
  allCharacters,
  characterIds = [],
  excludedCharacterIds = [],
  sortBy = "count",
  sortOrder = "desc",
  minMatches = 0,
  minUsage = 0,
  minWinRate = 0,
  bestResult = "",
  compositionBestResult = "",
  commanderBestResult = "",
  onTeamClick,
  selectedTeam
}: PaginatedTeamListProps) {
  const { t } = useI18n();

  const [teams, setTeams] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestGenerationRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);

  const limit = 10;

  const fetchTeams = async (currentOffset: number, reset: boolean, generation = requestGenerationRef.current) => {
    const controller = new AbortController();
    requestControllerRef.current?.abort();
    requestControllerRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
      const authHeaders: any = token ? { "Authorization": `Bearer ${token}` } : {};

      const isSingle = mode === "single" || (mode !== "cross" && tournamentId !== undefined);
      const targetId = tournamentId !== undefined ? tournamentId : tournamentIds[0];
      let res;
      if (isSingle && targetId) {
        let url = `/api/tournaments/${targetId}/dashboard/teams?limit=${limit}&offset=${currentOffset}&sort_by=${sortBy}&sort_order=${sortOrder}&registration_phase=${encodeURIComponent(registrationPhase)}`;
        if (characterIds.length > 0) {
          url += `&character_ids=${characterIds.join(",")}`;
        }
        if (excludedCharacterIds.length > 0) {
          url += `&excluded_character_ids=${excludedCharacterIds.join(",")}`;
        }
        if (minMatches > 0) url += `&min_matches=${minMatches}`;
        if (minUsage > 0) url += `&min_usage=${minUsage}`;
        if (minWinRate > 0) url += `&min_win_rate=${minWinRate}`;
        if (compositionBestResult) url += `&composition_best_result=${encodeURIComponent(compositionBestResult)}`;
        if (commanderBestResult) url += `&commander_best_result=${encodeURIComponent(commanderBestResult)}`;
        if (bestResult) url += `&best_result=${encodeURIComponent(bestResult)}`;
        res = await fetch(url, { headers: authHeaders, signal: controller.signal });
      } else {
        res = await fetch(`/api/dashboard/cross-tournament/teams`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify({
            tournament_ids: tournamentIds,
            registration_phase: registrationPhase,
            play_server: playServer,
            championship_id: championshipId,
            limit,
            offset: currentOffset,
            character_ids: characterIds.length > 0 ? characterIds : undefined,
            excluded_character_ids: excludedCharacterIds.length > 0 ? excludedCharacterIds : undefined,
            sort_by: sortBy,
            sort_order: sortOrder,
            min_matches: minMatches,
            min_usage: minUsage,
            min_win_rate: minWinRate,
            composition_best_result: compositionBestResult || undefined,
            commander_best_result: commanderBestResult || undefined,
            best_result: bestResult || undefined
          }),
          signal: controller.signal,
        });
      }
      if (generation !== requestGenerationRef.current) return;
      
      if (!res.ok) {
        console.error("API error in PaginatedTeamList:", res.status);
        if (res.status === 401) {
          setError(t('error.authRequired'));
        } else {
          setError(t('common.error'));
        }
        if (reset) setTeams([]);
        setTotal(0);
        setHasMore(false);
        return;
      }

      const data = await res.json();
      if (generation !== requestGenerationRef.current) return;
      const newTeams = Array.isArray(data.teams) ? data.teams : [];
      if (reset) {
        setTeams(newTeams);
      } else {
        setTeams(prev => [...prev, ...newTeams]);
      }
      setTotal(data.total || 0);
      setHasMore(currentOffset + newTeams.length < (data.total || 0));
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (generation !== requestGenerationRef.current) return;
      console.error("Failed to fetch teams", e);
      setError(t('common.error'));
    } finally {
      if (generation === requestGenerationRef.current) setLoading(false);
    }
  };

  // Reset and fetch when dependencies change
  useEffect(() => {
    const generation = requestGenerationRef.current + 1;
    requestGenerationRef.current = generation;
    requestControllerRef.current?.abort();
    if (tournamentIds.length === 0) {
      setTeams([]);
      setLoading(false);
      return;
    }
    setTeams([]);
    setError(null);
    setOffset(0);
    setHasMore(true);
    fetchTeams(0, true, generation);
    return () => requestControllerRef.current?.abort();
  }, [registrationPhase, mode, tournamentId, tournamentIds.join(","), playServer, championshipId, characterIds.join(","), excludedCharacterIds.join(","), sortBy, sortOrder, minMatches, minUsage, minWinRate, bestResult, compositionBestResult, commanderBestResult]);

  const handleLoadMore = () => {
    if (loading || !hasMore) return;
    const nextOffset = offset + limit;
    setOffset(nextOffset);
    fetchTeams(nextOffset, false);
  };

  if (teams.length === 0 && !loading) {
    return (
      <div className="text-center py-12 bg-slate-800/30 rounded-2xl ring-1 ring-white/5">
        <p className="text-slate-400 text-lg">{error || t('common.noData')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        {teams.map((team: any, idx: number) => {
          const ids = team.character_ids || team.characters?.map((c:any)=>c.id) || [];
          const normalized = [...ids].map(Number).sort((a,b)=>a-b);
          const selected = selectedTeam && [team.canonical_id, normalized.join("-"), normalized.join(",")].includes(selectedTeam);
          return <button type="button" key={`${team.registration_phase}-${team.canonical_id}-${idx}`} onClick={()=>onTeamClick(team.canonical_id,team)} className={`flex w-full flex-wrap items-center gap-x-4 gap-y-4 rounded-xl p-4 text-left transition-colors ${selected ? "bg-slate-700/80 ring-1 ring-emerald-500" : "bg-slate-800/50 ring-1 ring-white/5 hover:bg-slate-700/60"}`}>
            <div className="min-w-0 max-w-full flex-1 basis-60 space-y-2">
              <TeamDisplay charIds={ids} allCharacters={allCharacters}/>
              <div className="text-xs font-semibold text-blue-300"><RegistrationPhaseLabel phase={team.registration_phase}/></div>
            </div>
            <div className="grid w-full min-w-0 grid-cols-[minmax(0,1fr)_8rem] items-center gap-x-1 sm:w-auto sm:grid-cols-[8rem_10rem]">
            <div className="min-w-0 space-y-2 text-center">
              <CompositionBestResult team={team}/>
              <div className="flex flex-wrap justify-center gap-x-3 gap-y-1 text-xs text-slate-400"><span>{t("stats.usageCount")}: <strong className="text-slate-200">{team.count}</strong></span><span>{t("stats.matches")}: <strong className="text-slate-200">{team.total_matches ?? 0}</strong></span></div>

            </div>
            <div className={`rounded-xl px-4 py-3 text-center ${team.win_rate >= 50 ? "bg-emerald-400/10 text-emerald-300" : "bg-amber-400/10 text-amber-300"}`}>
              <div className="mb-1 text-xs font-semibold text-slate-400">{t("stats.winRate")}</div>
              <div className={team.total_matches > 0 ? "text-3xl font-black md:tabular-nums" : "text-sm font-bold"}>{team.total_matches > 0 && team.win_rate != null ? `${team.win_rate}%` : t("stats.noMatchRecords")}</div>
            </div>
            </div>
          </button>;
        })}
      </div>

      {hasMore && (
        <button
          onClick={handleLoadMore}
          disabled={loading}
          className="w-full py-4 bg-slate-800/80 hover:bg-slate-700 text-slate-300 font-bold rounded-xl ring-1 ring-white/10 transition-colors disabled:opacity-50"
        >
          {loading ? t('common.loading') : t('common.showMore')}
        </button>
      )}
    </div>
  );
}
