"use client";
import CompositionDetails from "@/components/CompositionDetails";
import TrendsRankings from "@/components/TrendsRankings";
import {useTeamSearchUsage} from "@/hooks/useTeamSearchUsage";
import { TeamRegistrationUsage, RegistrationPhaseLabel, CompositionBestResult, TeamBestResults, TeamResultFilters, TeamSearchFilters, WIN_RATE_FILTER_CLASS } from "@/components/TeamStatisticsMeaning";
export const dynamic = 'force-dynamic';
import { useState, useEffect, useRef, Suspense } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { ChevronDown, ChevronLeft, SlidersHorizontal, TrendingUp, Users, Swords, Search, X, Trophy, Globe } from "lucide-react";
import Link from "../components/LocalizedLink";
import PaginatedTeamList from "../components/PaginatedTeamList";
import SharedTeamDisplay from "../components/TeamDisplay";
import CharacterUsageByResultRanking from "../components/CharacterUsageByResultRanking";
import TeamAdoptionRanking from "../components/TeamAdoptionRanking";
import SynergyCharacterPicker, { ArenaCharacterDisplaySelect, SynergyPickerInstructions, useResetSynergyOnAnalysisChange } from "../components/SynergyCharacterPicker";
import { emptySynergySelection } from "../lib/synergyCharacters";
import type { ArenaCharacterDisplayMode } from "../lib/synergyCharacters";
import { useAuth } from "../context/AuthContext";
import { getCharIconUrl } from "@/utils/charIcon";
import { useI18n } from "@/i18n/I18nProvider";
import { localizedTournamentResult } from "@/lib/tournamentResult";

const SERVER_LABELS: Record<string, string> = {
  KR: "server.kr",
  JP: "server.jp",
  GLOBAL: "server.global",
  NA: "server.na",
  SEA: "server.sea",
};

type DashboardTab = "my_dashboard" | "overview" | "winrate" | "team_winrate" | "matchups" | "search" | "best8";
const PUBLIC_TABS = new Set<DashboardTab>(["team_winrate", "matchups", "search", "overview"]);

function PlayerAvatar({ url, seed }: { url?: string | null; seed: number }) {
  const [failed, setFailed] = useState(false);

  return (
    <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center mb-2 font-black text-slate-300 ring-1 ring-white/10 group-hover:ring-amber-400 transition-colors shadow-lg overflow-hidden shrink-0">
      {url && !failed ? (
        <img
          src={url}
          alt=""
          className="w-full h-full object-cover"
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      ) : (
        seed
      )}
    </div>
  );
}

function DashboardContent() {
  const { t } = useI18n();
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const router = useRouter();

  // URLクエリパラメータから初期タブ・編成を復元（キャラ詳細ページからの遷移用）
  const requestedTab = searchParams.get("tab") as DashboardTab | null;
  const [registrationPhase, setRegistrationPhase] = useState(() => {
    const phase = searchParams.get("registration_phase");
    return phase && ["legacy", "league", "championship", "final"].includes(phase) ? phase : phase === "initial" ? "league" : "championship";
  });
  const previousRegistrationPhase = useRef(registrationPhase);
  useEffect(() => {
    if (previousRegistrationPhase.current === registrationPhase) return;
    previousRegistrationPhase.current = registrationPhase;
    setSelectedCharId(null);
  }, [registrationPhase]);

  const initialTab = requestedTab && PUBLIC_TABS.has(requestedTab)
    ? requestedTab
    : "team_winrate";
  const initialTeam = searchParams.get("teamKey") || searchParams.get("team");

  const [tournament, setTournament] = useState<any>(null);
  const [allCharacters, setAllCharacters] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // 大会データとそのフィルタリング
  const [allTournaments, setAllTournaments] = useState<any[]>([]);
  const [filterServer, setFilterServer] = useState<string>("JP");
  const [filterSeason, setFilterSeason] = useState<string>("");
  const [isAllTournamentsSelected, setIsAllTournamentsSelected] = useState<boolean>(true);
  const [selectedSpecificTournamentIds, setSelectedSpecificTournamentIds] = useState<number[]>([]);
  const [selectedTournamentIds, setSelectedTournamentIds] = useState<number[]>([]);
  const [isMobileFiltersOpen, setIsMobileFiltersOpen] = useState(false);
  
  // The public top page exposes only aggregate analysis tabs.
  const [activeTab, setActiveTab] = useState<DashboardTab>(initialTab);

  // For matchups
  const [selectedTeam, setSelectedTeam] = useState<string>(initialTeam || "");
  const [detailPhase, setDetailPhase] = useState(() => searchParams.get("detail_phase") ?? (requestedTab === "matchups" ? searchParams.get("registration_phase") : null) ?? "all");
  // For search
  const initialSynergy = searchParams.get("synergy")
    ? searchParams.get("synergy")!.split(",").map(x => parseInt(x.trim(), 10)).filter(x => !isNaN(x))
    : [];
  const [includedCharacterIds, setIncludedCharacterIds] = useState<number[]>(initialSynergy);
  const [excludedCharacterIds, setExcludedCharacterIds] = useState<number[]>([]);
  const [filterRarity, setFilterRarity] = useState<string>("");
  const [filterManufacturer, setFilterManufacturer] = useState<string>("");
  const [filterBurst, setFilterBurst] = useState<string>("");
  const [filterElement, setFilterElement] = useState<string>("");
  const [filterWeapon, setFilterWeapon] = useState<string>("");
  const [arenaCharacterDisplay, setArenaCharacterDisplay] = useState<ArenaCharacterDisplayMode>("only");

  // For winrate filters
  const [winrateMinMatches, setWinrateMinMatches] = useState<number>(1);
  const [winrateBurstPhase, setWinrateBurstPhase] = useState<string>("");
  const [winrateWeapon, setWinrateWeapon] = useState<string>("");
  const [winrateElement, setWinrateElement] = useState<string>("");
  const [winrateManufacturer, setWinrateManufacturer] = useState<string>("");

  // For team filters
  const [teamMinMatches, setTeamMinMatches] = useState<number>(10);
  const [winRateStage, setWinRateStage] = useState("all");
  const [searchStage,setSearchStage]=useState("all");
  const [searchSort,setSearchSort]=useState<"count"|"win_rate"|"composition_best_result">("count");
  const [searchComposition,setSearchComposition]=useState("");
  const [searchWinRate,setSearchWinRate]=useState(0);
  const [teamCompositionBestResult, setTeamCompositionBestResult] = useState<string>("");
    const [teamMinWinRate, setTeamMinWinRate] = useState<number>(0);
  
  // For Character Modal
  const [selectedCharId, setSelectedCharId] = useState<number | null>(null);
  const [selectedCharacterDetail, setSelectedCharacterDetail] = useState<any>(null);
  const [selectedCharacterDetailLoading, setSelectedCharacterDetailLoading] = useState(false);

  // For My Dashboard Tab Search
  const [seedSearchQuery, setSeedSearchQuery] = useState<string>("");

  const handleTeamClick = (canonicalId: string, team?: any) => {
    if (!canonicalId) return;
    const phase = team?.registration_phase ?? "all";
    setSelectedTeam(canonicalId);
    setDetailPhase(phase);
    setActiveTab("matchups");
    setSelectedCharId(null);
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "matchups");
    params.set("detail_phase", phase);
    params.set("team", canonicalId);
    params.delete("teamKey");
    if (selectedTournamentIds.length) params.set("tournaments", selectedTournamentIds.join(","));
    router.push("/?" + params.toString(), { scroll: false });
  };

  // 分析対象のシード番号 (1-64)
  const [selectedSeed, setSelectedSeed] = useState<number>(1);
  const [isFirstLoad, setIsFirstLoad] = useState(true);
  const seeds = Array.from({length: 64}, (_, i) => i + 1);

  useEffect(() => {
    const savedSeed = localStorage.getItem(`nikke_dashboard_seed_cross`);
    if (savedSeed) {
      setSelectedSeed(parseInt(savedSeed));
    }
    setIsFirstLoad(false);
  }, []);

  // 2. シードが変更されたら localStorage に保存
  useEffect(() => {
    if (!isFirstLoad) {
      localStorage.setItem(`nikke_dashboard_seed_cross`, selectedSeed.toString());
    }
  }, [selectedSeed, isFirstLoad]);

  // 大会リストの初回取得と選択状態の初期化
  useEffect(() => {
    if (isFirstLoad) return;
    const fetchTournaments = async () => {
      try {
        const res = await fetch(`/api/tournaments?t=${Date.now()}`, { cache: 'no-store' });
        if (!res.ok) {
          setLoading(false);
          return;
        }
        const data: any[] = await res.json();
        if (!Array.isArray(data)) {
          setLoading(false);
          return;
        }
        setAllTournaments(data);
        
        if (data.length > 0) {
          const availableServers = new Set(data.map(t => t.play_server).filter(Boolean));
          
          const savedServer = localStorage.getItem('nikke_filter_server');
          const savedSeason = localStorage.getItem('nikke_filter_season');
          const savedIsAll = localStorage.getItem('nikke_filter_is_all');
          const savedSpecificIdsStr = localStorage.getItem('nikke_filter_specific_ids');

          const fallbackServer = availableServers.has("JP") ? "JP" : Array.from(availableServers)[0] as string | undefined;
          const initialServer = (savedServer && availableServers.has(savedServer)) ? savedServer : (fallbackServer || "");
          setFilterServer(initialServer);

          const serverTournaments = data.filter(t => t.play_server === initialServer);
          const serverSeasons = new Set(serverTournaments.map(t => t.season || "β30").filter(Boolean));
          
          const latest = serverTournaments.length > 0 ? serverTournaments.reduce((current, tournament) => {
            const currentTime = new Date(current.date || current.created_at || 0).getTime();
            const tournamentTime = new Date(tournament.date || tournament.created_at || 0).getTime();
            return tournamentTime > currentTime ? tournament : current;
          }) : null;
          const initialSeasonFallback = latest?.season || "β30";

          const initialSeason = (savedSeason && serverSeasons.has(savedSeason)) ? savedSeason : initialSeasonFallback;
          setFilterSeason(initialSeason);

          if (savedIsAll !== null) {
            setIsAllTournamentsSelected(savedIsAll === "true");
          }
          if (savedSpecificIdsStr) {
            try {
              setSelectedSpecificTournamentIds(JSON.parse(savedSpecificIdsStr));
            } catch (e) {}
          }
        } else {
          // 大会データが0件のとき、ローディングを終了する
          setLoading(false);
        }
      } catch (e) {
        console.error(e);
        // エラー時もローディングを終了する
      } finally {
        setLoading(false);
      }
    };
    fetchTournaments();
  }, [isFirstLoad, user?.game_start_date]);

  const seasonTournaments = allTournaments.filter(item => item.play_server === filterServer && (item.season || "β30") === filterSeason);
  const hasFormal = seasonTournaments.some(item => item.deck_registration_phases);
  const changeRegistrationPhase = (phase:string) => {
    setRegistrationPhase(phase);
    const query = new URLSearchParams(searchParams.toString()); query.set("registration_phase",phase);
    router.replace(`/?${query.toString()}`,{scroll:false});
  };
  useEffect(()=>{
    if (!seasonTournaments.length) return;
    if (!hasFormal && registrationPhase !== "legacy") changeRegistrationPhase("legacy");
    else if (hasFormal && registrationPhase === "legacy") changeRegistrationPhase("championship");
  },[hasFormal,seasonTournaments.length]);
  const selectedChampionshipId = seasonTournaments[0]?.championship_id;
  const hasSelectedFormal = allTournaments.some(item=>selectedTournamentIds.includes(item.id) && Boolean(item.deck_registration_phases));
  const analysisKey = allTournaments.length > 0 && selectedChampionshipId && selectedTournamentIds.length > 0
    ? [filterServer, filterSeason, selectedChampionshipId, [...selectedTournamentIds].sort((a, b) => a - b).join(",")].join("|")
    : null;
  useResetSynergyOnAnalysisChange(analysisKey, () => {
    setIncludedCharacterIds([]);
    setExcludedCharacterIds([]);
  });

  // フィルタ状態から selectedTournamentIds を計算
  useEffect(() => {
    if (allTournaments.length === 0) return;
    let filtered = allTournaments.filter(t => (t.play_server || "") === filterServer && (t.season || "β30") === filterSeason);
    
    if (isAllTournamentsSelected) {
      setSelectedTournamentIds(filtered.map(t => t.id));
    } else {
      const validSpecificIds = selectedSpecificTournamentIds.filter(id => filtered.some(t => t.id === id));
      setSelectedTournamentIds(validSpecificIds.length > 0 ? validSpecificIds : filtered.map(t => t.id));
    }
  }, [filterServer, filterSeason, isAllTournamentsSelected, selectedSpecificTournamentIds, allTournaments, registrationPhase]);

  // フィルタ状態を localStorage に保存
  useEffect(() => {
    if (isFirstLoad || allTournaments.length === 0) return;
    localStorage.setItem('nikke_filter_server', filterServer);
    localStorage.setItem('nikke_filter_season', filterSeason);
    localStorage.setItem('nikke_filter_is_all', isAllTournamentsSelected.toString());
    localStorage.setItem('nikke_filter_specific_ids', JSON.stringify(selectedSpecificTournamentIds));
  }, [filterServer, filterSeason, isAllTournamentsSelected, selectedSpecificTournamentIds, allTournaments, isFirstLoad]);

  useEffect(() => {
    if (!selectedCharId || selectedTournamentIds.length === 0) {
      setSelectedCharacterDetail(null);
      return;
    }

    const controller = new AbortController();
    const fetchCharacterDetail = async () => {
      setSelectedCharacterDetailLoading(true);
      try {
        const res = await fetch("/api/dashboard/cross-tournament/character-detail", {
          method: "POST",
          signal: controller.signal,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            character_id: selectedCharId,
            registration_phase: registrationPhase,
            tournament_ids: selectedTournamentIds,
            play_server: filterServer,
            championship_id: selectedChampionshipId,
          }),
        });

        if (!res.ok) {
          const text = await res.text();
          console.error("character detail API error", res.status, text.slice(0, 300));
          return;
        }

        const data = await res.json();
        if (!controller.signal.aborted) setSelectedCharacterDetail(data);
      } catch (e) {
        if (controller.signal.aborted) return;
        console.error("failed to fetch selected character detail", e);
      } finally {
        if (!controller.signal.aborted) setSelectedCharacterDetailLoading(false);
      }
    };

    fetchCharacterDetail();
    return () => controller.abort();
  }, [selectedCharId, selectedTournamentIds, filterServer, selectedChampionshipId, registrationPhase]);

  useEffect(() => {
    if (!selectedCharId) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelectedCharId(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedCharId]);

  useEffect(() => {
    const controller = new AbortController();
    const fetchCharacters = async () => {
      try {
        const charsRes = await fetch("/api/characters", {
          cache: "no-store",
          signal: controller.signal,
        });
        if (charsRes.ok) setAllCharacters(await charsRes.json());
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        console.error(error);
      }
    };
    void fetchCharacters();
    return () => controller.abort();
  }, []);

  const searchCandidates=useTeamSearchUsage(activeTab === "search", selectedTournamentIds, undefined, filterServer, selectedChampionshipId);

  if (loading) return (
    <div className="flex h-screen items-center justify-center">
      <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );

  if (allTournaments.length === 0) {
    return (
      <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 font-sans">
        <main className="flex-1 max-w-4xl mx-auto px-4 py-16 flex flex-col items-center justify-center text-center">
          <div className="w-24 h-24 rounded-3xl bg-slate-900 border border-white/10 flex items-center justify-center mb-8 shadow-2xl">
            <span className="text-4xl">📊</span>
          </div>
          <h1 className="text-3xl font-black mb-4 tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
            {t('empty.welcome')}
          </h1>
          <p className="text-slate-400 text-base max-w-md mb-8 leading-relaxed">
            {t('empty.noTournaments')}<br />
            {t('empty.registerHint')}
          </p>
          <a href="/tournaments/manage" className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold transition-all shadow-xl shadow-blue-500/20">
            <span>{t('empty.registerAction')}</span>
          </a>
        </main>
      </div>
    );
  }

  // Helper to render a team
  const TeamDisplay = ({ charIds, allCharacters: charsParam }: { charIds: number[], allCharacters?: any[] }) => {
    const chars = charsParam || allCharacters;
    const displayChars = charIds.map(cid => chars.find((c: any) => c.id === cid) || { id: cid, name: String(cid), is_template_available: cid !== 9999 });
    return (
      <div className="flex space-x-2">
        {displayChars.map((c: any, i: number) => {
          if (c.id === 9999) {
            return (
              <div key={i} className="flex flex-col items-center space-y-1 opacity-50">
                <div className="w-10 h-10 rounded-lg bg-slate-800/50 ring-1 ring-white/5 overflow-hidden flex items-center justify-center">
                  <div className="text-slate-600 text-xs">-</div>
                </div>
                <span className="text-[9px] text-slate-500 w-10 truncate text-center" title={t('character.emptySlot')}>{t('character.emptySlot')}</span>
              </div>
            );
          }
          return (
            <div key={i} className="flex flex-col items-center space-y-1 cursor-pointer group" onClick={(e) => { e.stopPropagation(); setSelectedCharId(c.id); }}>
              <div className="w-10 h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 group-hover:ring-blue-500 overflow-hidden flex items-center justify-center transition-all">
                {getCharIconUrl(c) ? (
                  <img src={getCharIconUrl(c)} loading="lazy" decoding="async" alt={c?.name || t('common.unknown')} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-[10px] text-slate-500 font-bold leading-tight text-center">{c?.name?.slice(0, 3) || t('common.unknown')}</span>
                )}
              </div>
              <span className="text-[9px] text-slate-400 w-10 truncate text-center" title={c?.name || t('common.unknown')}>{c?.name || t('common.unknown')}</span>
            </div>
          );
        })}
      </div>
    );
  };

  const registrationScopeByTournamentId = Object.fromEntries(
    allTournaments.filter(item => selectedTournamentIds.includes(Number(item.id)) && item.deck_registration_phases)
      .map(item => [Number(item.id), item.registration_scope]),
  );

  const seasons = Array.from(new Set(allTournaments.map(t => t.season || "β30")));
  const playServers = Object.keys(SERVER_LABELS);
  const availableServers = new Set(allTournaments.map(t => t.play_server).filter(Boolean));
  const gameStartDates = Array.from(new Set(
    allTournaments.map(t => t.provider_game_start_date).filter(Boolean)
  )).sort() as string[];

  return (
    <main className="p-3 sm:p-4 md:p-8 max-w-[1400px] mx-auto space-y-4 md:space-y-8 pb-24 overflow-x-hidden">
      <h1 className="sr-only">{t('dashboard.title')}</h1>



      <div className="flex flex-col xl:flex-row gap-4 xl:gap-8">
        {/* Sidebar for Filters */}
        <aside className="w-full xl:w-64 shrink-0 space-y-3 xl:space-y-6">
          <button
            type="button"
            onClick={() => setIsMobileFiltersOpen(open => !open)}
            className="flex min-h-14 w-full items-center gap-3 rounded-lg bg-slate-900/90 px-4 py-3 text-left ring-1 ring-white/10 xl:hidden"
            aria-expanded={isMobileFiltersOpen}
            aria-controls="mobile-dashboard-filters"
          >
            <SlidersHorizontal className="h-5 w-5 shrink-0 text-blue-400" />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-bold text-slate-100">{t('filter.title')}</span>
              <span className="block truncate text-xs text-slate-400">
                {t('filter.analysisTarget', { server: SERVER_LABELS[filterServer] ? t(SERVER_LABELS[filterServer]) : filterServer, season: filterSeason, tournaments: isAllTournamentsSelected ? t('filter.allTournaments', { count: allTournaments.filter(item => item.play_server === filterServer && (item.season || "β30") === filterSeason).length }) : t('filter.tournamentCount', { count: selectedTournamentIds.length }) })}
              </span>
            </span>
            <span className="shrink-0 rounded bg-blue-500/15 px-2 py-1 text-xs font-bold text-blue-300">
              {t('filter.tournamentCount', { count: selectedTournamentIds.length })}
            </span>
            <ChevronDown className={`h-5 w-5 shrink-0 text-slate-400 transition-transform ${isMobileFiltersOpen ? "rotate-180" : ""}`} />
          </button>

          <div
            id="mobile-dashboard-filters"
            className={`${isMobileFiltersOpen ? "block" : "hidden"} bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-4 sm:p-5 xl:p-6 rounded-lg sm:rounded-xl xl:rounded-3xl shadow-2xl xl:sticky xl:top-6 xl:block`}
          >
            <h3 className="hidden text-lg font-bold text-slate-100 mb-6 xl:flex items-center space-x-2">
              <Search size={18} className="text-blue-400" />
              <span>{t('filter.title')}</span>
            </h3>
            

            <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 xl:block xl:space-y-6">
              <div>
                <div className="text-xs font-bold text-slate-500 mb-3 uppercase tracking-wider">{t('filter.server')}</div>
                <select 
                  value={filterServer}
                  onChange={(e) => {
                    const newServer = e.target.value;
                    if (newServer === filterServer) return;
                    setFilterServer(newServer);
                    const newServerTournaments = allTournaments.filter(t => t.play_server === newServer);
                    const newServerSeasons = Array.from(new Set(newServerTournaments.map(t => t.season || "β30").filter(Boolean)));
                    if (newServerSeasons.length > 0 && !newServerSeasons.includes(filterSeason)) {
                      setFilterSeason(newServerSeasons[0] as string);
                    }
                    setIsAllTournamentsSelected(true);
                    setSelectedSpecificTournamentIds([]);
                  }}
                  className="w-full bg-slate-800 text-slate-200 text-sm rounded-lg border border-white/10 px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                >
                  {playServers.map(server => (
                    <option key={server} value={server} disabled={!availableServers.has(server)}>
                      {SERVER_LABELS[server] ? t(SERVER_LABELS[server]) : server}
                    </option>
                  ))}
                </select>
              </div>

              <div className="hidden h-px w-full bg-white/10 xl:block"></div>

              <div>
                <div className="text-xs font-bold text-slate-500 mb-3 uppercase tracking-wider">{t('filter.season')}</div>
                <select
                  value={filterSeason}
                  onChange={(e) => {
                    const newSeason = e.target.value;
                    if (newSeason === filterSeason) return;
                    setFilterSeason(newSeason);
                    setIsAllTournamentsSelected(true);
                    setSelectedSpecificTournamentIds([]);
                  }}
                  className="w-full bg-slate-800 text-slate-200 text-sm rounded-lg border border-white/10 px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                >
                  {Array.from(new Set(allTournaments.filter(t => t.play_server === filterServer).map(t => t.season || "β30").filter(Boolean))).map((s: any) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              <div className="hidden h-px w-full bg-white/10 xl:block"></div>

              <div>
                <div className="text-xs font-bold text-slate-500 mb-3 uppercase tracking-wider">{t('filter.tournaments')}</div>
                <div className="flex items-center space-x-4 mb-3 px-1">
                  <label className="flex items-center space-x-2 cursor-pointer group">
                    <input type="radio" 
                      checked={isAllTournamentsSelected} 
                      onChange={() => setIsAllTournamentsSelected(true)}
                      className="w-4 h-4 text-blue-500 bg-slate-800 border-white/20 focus:ring-blue-500 focus:ring-offset-slate-900" 
                    />
                    <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">{t('common.all')}</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer group">
                    <input type="radio" 
                      checked={!isAllTournamentsSelected} 
                      onChange={() => setIsAllTournamentsSelected(false)}
                      className="w-4 h-4 text-blue-500 bg-slate-800 border-white/20 focus:ring-blue-500 focus:ring-offset-slate-900" 
                    />
                    <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">{t('filter.individual')}</span>
                  </label>
                </div>
                
                {!isAllTournamentsSelected && (
                  <div className="space-y-2.5 max-h-48 overflow-y-auto pr-2 custom-scrollbar mt-2 bg-slate-950/30 p-2 rounded-lg ring-1 ring-white/5">
                    {allTournaments
                      .filter(t => (t.play_server || "") === filterServer && (t.season || "β30") === filterSeason)
                      .sort((a, b) => new Date(a.provider_game_start_date || 0).getTime() - new Date(b.provider_game_start_date || 0).getTime())
                      .map(tournament => (
                      <label key={tournament.id} className="flex items-center space-x-3 cursor-pointer group">
                        <input type="checkbox" checked={selectedSpecificTournamentIds.includes(tournament.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedSpecificTournamentIds([...selectedSpecificTournamentIds, tournament.id]);
                            } else {
                              setSelectedSpecificTournamentIds(selectedSpecificTournamentIds.filter(id => id !== tournament.id));
                            }
                          }}
                          className="w-4 h-4 rounded bg-slate-800 border-white/20 text-emerald-500 focus:ring-emerald-500 focus:ring-offset-slate-900 transition-colors cursor-pointer"
                        />
                        <span className="text-xs font-medium text-slate-300 group-hover:text-white transition-colors truncate">
                          {tournament.provider_game_start_date ? t('filter.startedAt', { date: tournament.provider_game_start_date }) : (tournament.name || t('filter.tournamentFallback', { id: tournament.id }))}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
            
            <div className="hidden mt-8 p-4 rounded-xl bg-blue-500/10 ring-1 ring-blue-500/20 xl:block">
              <div className="text-xs text-blue-400 font-bold mb-1">{t('filter.targetTournamentCount')}</div>
              <div className="text-2xl font-black text-slate-100">{selectedTournamentIds.length}</div>
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <div className="flex-1 space-y-4 md:space-y-8 min-w-0">
          {/* Tabs */}
          <div className="sticky top-0 z-20 -mx-3 bg-slate-950/95 px-3 py-2 backdrop-blur-xl sm:-mx-4 sm:px-4 md:static md:mx-0 md:bg-transparent md:p-0">
          <div className="flex snap-x snap-mandatory bg-slate-900/80 backdrop-blur-xl p-1 rounded-lg md:p-1.5 md:rounded-2xl ring-1 ring-white/10 shadow-2xl overflow-x-auto hide-scrollbar">
            <button 
              onClick={() => setActiveTab("team_winrate")}
              className={`flex snap-start items-center space-x-1.5 px-3 py-2.5 text-xs md:space-x-2 md:px-6 md:py-3 md:text-base rounded-md md:rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "team_winrate" ? "bg-pink-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
            >
              <Users size={18} />
              <span>Win Rate</span>
            </button>
            <button 
              onClick={() => setActiveTab("matchups")}
              className={`flex snap-start items-center space-x-1.5 px-3 py-2.5 text-xs md:space-x-2 md:px-6 md:py-3 md:text-base rounded-md md:rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "matchups" ? "bg-purple-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
            >
              <Swords size={18} />
              <span>Details</span>
            </button>

            <button 
              onClick={() => setActiveTab("search")}
              className={`flex snap-start items-center space-x-1.5 px-3 py-2.5 text-xs md:space-x-2 md:px-6 md:py-3 md:text-base rounded-md md:rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "search" ? "bg-emerald-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
            >
              <Search size={18} />
              <span>Team Search</span>
            </button>
            <button
              onClick={() => setActiveTab("overview")}
              className={`flex snap-start items-center space-x-1.5 px-3 py-2.5 text-xs md:space-x-2 md:px-6 md:py-3 md:text-base rounded-md md:rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "overview" ? "bg-blue-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
            >
              <TrendingUp size={18} />
              <span>Trends</span>
            </button>
          </div>
          </div>

          {/* Content */}
          <div className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-3 sm:p-4 md:p-8 rounded-lg sm:rounded-xl md:rounded-3xl shadow-2xl min-h-[500px]">
        {/* OVERVIEW TAB */}
        {activeTab === "overview" && <TrendsRankings formal={hasSelectedFormal} tournamentIds={selectedTournamentIds} allCharacters={allCharacters} onSelectCharacter={setSelectedCharId} onTeamClick={handleTeamClick}/>}

        {/* TEAM WINRATE TAB */}
        {activeTab === "team_winrate" && (
           <div className="space-y-12 animate-in fade-in zoom-in-95 duration-300">
            <section>
              <div className="mb-6 flex flex-col gap-4">
                <h2 className="text-xl font-bold text-white flex items-center space-x-2">
                  <Trophy className="text-emerald-400" />
                  <span>{t('stats.teamWinRateRanking')}</span>
                </h2>
                
                {/* 編成フィルタコントロール群 */}
                <div className="flex flex-wrap gap-2 items-center">
                  <select
                    value={teamMinMatches}
                    onChange={(e) => setTeamMinMatches(Number(e.target.value))}
                    className={WIN_RATE_FILTER_CLASS}
                  >
                    {[0, 1, 10, 30, 50].map((count) => <option key={count} value={count}>{t('filter.matchesAtLeast', { count })}</option>)}
                  </select>

                  <select
                    value={teamMinWinRate}
                    onChange={(e) => setTeamMinWinRate(Number(e.target.value))}
                    className={WIN_RATE_FILTER_CLASS}
                  >
                    <option value={0}>{t('filter.winRateAny')}</option>
                    {[50, 60, 70, 80].map((rate) => <option key={rate} value={rate}>{t('filter.winRateAtLeast', { rate })}</option>)}
                  </select>

                  <TeamResultFilters composition={teamCompositionBestResult} onCompositionChange={setTeamCompositionBestResult} stage={winRateStage} onStageChange={setWinRateStage} formal={hasSelectedFormal}/>
                </div>
              </div>

              <div className="space-y-3">
                <PaginatedTeamList registrationPhase={hasSelectedFormal ? winRateStage : "all"}
                  mode="cross"
                  tournamentIds={selectedTournamentIds} 
                  playServer={filterServer}
                  championshipId={selectedChampionshipId}
                  allCharacters={allCharacters}
                  onTeamClick={handleTeamClick} 
                  selectedTeam={selectedTeam} 
                  sortBy="win_rate"
                  minMatches={teamMinMatches}
                  
                  minWinRate={teamMinWinRate}
                  compositionBestResult={teamCompositionBestResult}
                />
              </div>
            </section>
          </div>
        )}

        {activeTab === "matchups" && <CompositionDetails
          tournamentIds={selectedTournamentIds} playServer={filterServer} championshipId={selectedChampionshipId}
          formal={hasSelectedFormal} phase={detailPhase} canonicalId={selectedTeam}
          onPhaseChange={setDetailPhase} onTeamChange={setSelectedTeam}
          allCharacters={allCharacters} onSelectCharacter={setSelectedCharId}
          registrationScopeByTournamentId={registrationScopeByTournamentId}/>}

        {/* SEARCH TAB */}
        {activeTab === "search" && (() => {
          const filteredCharacters = allCharacters.filter(c => {
            if (c.id === 9999) return false;
            if (filterRarity && c.rarity !== filterRarity) return false;
            if (filterManufacturer && c.manufacturer !== filterManufacturer) return false;
            if (filterElement && c.element !== filterElement) return false;
            if (filterWeapon && c.weapon !== filterWeapon) return false;
            if (filterBurst) {
              if (filterBurst === "1" && c.burst_phase !== "1" && c.burst_phase !== "A") return false;
              if (filterBurst === "2" && c.burst_phase !== "2" && c.burst_phase !== "A") return false;
              if (filterBurst === "3" && c.burst_phase !== "3" && c.burst_phase !== "A") return false;
            }
            return true;
          });

          return (
          <div className="space-y-8 animate-in fade-in zoom-in-95 duration-300">
            <div className="bg-emerald-500/10 p-6 rounded-2xl ring-1 ring-emerald-500/20">
              <SynergyPickerInstructions />

              <ArenaCharacterDisplaySelect
                value={arenaCharacterDisplay}
                onChange={setArenaCharacterDisplay}
              />

              {/* フィルターUI */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterRarity} onChange={e => setFilterRarity(e.target.value)}>
                  <option value="">{t('filter.rarity')} ({t('common.all')})</option>
                  <option value="SSR">SSR</option>
                  <option value="SR">SR</option>
                  <option value="R">R</option>
                </select>
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterManufacturer} onChange={e => setFilterManufacturer(e.target.value)}>
                  <option value="">{t('filter.manufacturer')} ({t('common.all')})</option>
                  <option value="エリシオン">{t('manufacturer.elysion')}</option>
                  <option value="ミシリス">{t('manufacturer.missilis')}</option>
                  <option value="テトラ">{t('manufacturer.tetra')}</option>
                  <option value="ピルグリム">{t('manufacturer.pilgrim')}</option>
                  <option value="アブノーマル">{t('manufacturer.abnormal')}</option>
                </select>
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterBurst} onChange={e => setFilterBurst(e.target.value)}>
                  <option value="">{t('filter.burst')} ({t('common.all')})</option>
                  {[1, 2, 3].map((value) => <option key={value} value={value}>{t('filter.includesAlternate', { value })}</option>)}
                </select>
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterElement} onChange={e => setFilterElement(e.target.value)}>
                  <option value="">{t('filter.element')} ({t('common.all')})</option>
                  <option value="灼熱">{t('element.fire')}</option>
                  <option value="水冷">{t('element.water')}</option>
                  <option value="風圧">{t('element.wind')}</option>
                  <option value="鉄甲">{t('element.iron')}</option>
                  <option value="電撃">{t('element.electric')}</option>
                </select>
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterWeapon} onChange={e => setFilterWeapon(e.target.value)}>
                  <option value="">{t('filter.weapon')} ({t('common.all')})</option>
                  <option value="AR">{t('weapon.ar')}</option>
                  <option value="SG">{t('weapon.sg')}</option>
                  <option value="SMG">{t('weapon.smg')}</option>
                  <option value="MG">{t('weapon.mg')}</option>
                  <option value="SR">{t('weapon.sr')}</option>
                  <option value="RL">{t('weapon.rl')}</option>
                </select>
              </div>

              <SynergyCharacterPicker
                key={`synergy-picker-cross-${analysisKey}`}
                characters={filteredCharacters}
                characterUsage={searchCandidates.usage}
                usageState={searchCandidates.state}
                includedIds={includedCharacterIds}
                excludedIds={excludedCharacterIds}
                displayMode={arenaCharacterDisplay}
                onChange={({ includedIds, excludedIds }) => {
                  setIncludedCharacterIds(includedIds);
                  setExcludedCharacterIds(excludedIds);
                }}
              />
              <div className="mt-4 flex items-center justify-between border-t border-emerald-500/20 pt-4">
                <span className="text-sm text-slate-400">{t('search.target')}: {includedCharacterIds.length}/5　{t('search.exclude')}: {excludedCharacterIds.length}</span>
                {(includedCharacterIds.length > 0 || excludedCharacterIds.length > 0) && (
                  <button onClick={() => { const cleared = emptySynergySelection(); setIncludedCharacterIds(cleared.includedIds); setExcludedCharacterIds(cleared.excludedIds); }} className="text-sm text-emerald-400 hover:text-emerald-300 font-bold">
                    {t('common.clear')}
                  </button>
                )}
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="font-bold text-white mb-4">{t('search.results')}</h3>
              <TeamSearchFilters sort={searchSort} onSortChange={setSearchSort} stage={searchStage} onStageChange={setSearchStage} composition={searchComposition} onCompositionChange={setSearchComposition} winRate={searchWinRate} onWinRateChange={setSearchWinRate} formal={hasSelectedFormal}/>
              {includedCharacterIds.length === 0 ? (
                <p className="text-slate-500 text-center py-12">{t('search.selectOne')}</p>
              ) : (
                <div className="space-y-3">
                  <PaginatedTeamList registrationPhase={hasSelectedFormal ? searchStage : "all"}
                    key={`synergy-cross-${analysisKey}-${includedCharacterIds.join(",")}-${excludedCharacterIds.join(",")}`}
                    mode="cross"
                    tournamentIds={selectedTournamentIds} 
                    playServer={filterServer}
                    championshipId={selectedChampionshipId}
                    allCharacters={allCharacters}
                    characterIds={includedCharacterIds}
                    excludedCharacterIds={excludedCharacterIds}
                    onTeamClick={canonicalId => handleTeamClick(canonicalId)}
                    selectedTeam={selectedTeam} 
                    sortBy={searchSort}
                    compositionBestResult={searchComposition}
                    minWinRate={searchWinRate}
                  />
                </div>
              )}
            </div>
          </div>
        )})()}
      </div>
    </div>
  </div>

  {/* Character Details Modal */}
      {selectedCharId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
          onClick={() => setSelectedCharId(null)}
        >
          <div
            className="bg-slate-900 ring-1 ring-white/10 rounded-3xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl relative"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 z-50 flex justify-end p-4 -mb-14 pointer-events-none">
              <button
                onClick={() => setSelectedCharId(null)}
                className="pointer-events-auto flex h-10 w-10 items-center justify-center rounded-full bg-slate-900/90 text-slate-300 ring-1 ring-white/20 shadow-xl backdrop-blur hover:bg-slate-800 hover:text-white transition-all"
                aria-label={t('common.close')}
              >
                <X size={20} />
              </button>
            </div>
            {selectedCharacterDetailLoading ? (
              <div className="p-16 flex flex-col items-center justify-center space-y-4">
                <div className="animate-spin w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full" />
                <p className="text-slate-400 text-sm font-bold">{t('character.loadingDetails')}</p>
              </div>
            ) : (() => {
              const c = allCharacters.find(x => x.id === selectedCharId);
              if (!c) return null;
              
              const usageData = selectedCharacterDetail?.character_usage?.[0];
              const relatedTeams = (selectedCharacterDetail?.team_usage ?? []).map((t: any) => ({
                ...t,
                character_ids: t.character_ids || (t.characters || []).map((ch: any) => typeof ch === 'object' ? ch.id : ch)
              }));
              const usageCount = usageData?.count || 0;
              const winRate = usageData?.total_matches > 0 ? usageData.win_rate : null;
              const charWins = usageData?.win_count || 0;
              const totalMatches = usageData?.total_matches || 0;
              const charLosses = totalMatches - charWins;
              const hasPositionStats = Array.isArray(usageData?.position_stats) && usageData.position_stats.length > 0;
              const hasTeamPositionStats = Array.isArray(usageData?.team_position_stats) && usageData.team_position_stats.length > 0;

              const synergyCounts: Record<number, number> = {};
              relatedTeams.forEach((t: any) => {
                (t.character_ids || []).forEach((cid: number) => {
                  if (Number(cid) !== Number(selectedCharId)) {
                    synergyCounts[Number(cid)] = (synergyCounts[Number(cid)] || 0) + (t.count || 0);
                  }
                });
              });

              const synergisticChars = Object.entries(synergyCounts)
                .map(([idStr, count]) => {
                  const ch = allCharacters.find(x => x.id === Number(idStr));
                  return { ...ch, synergyCount: count as number };
                })
                .filter(ch => ch.id)
                .sort((a: any, b: any) => b.synergyCount - a.synergyCount);

              const burst1Chars = synergisticChars.filter((ch: any) => ch.burst_phase === "1");
              const burst2Chars = synergisticChars.filter((ch: any) => ch.burst_phase === "2");
              const burst3Chars = synergisticChars.filter((ch: any) => ch.burst_phase === "3");

              return (
                <div className="p-6 sm:p-8 space-y-8 animate-in fade-in zoom-in-95 duration-200">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pr-12 sm:pr-14">
                    <div className="flex items-center space-x-4 sm:space-x-6">
                      <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-2xl bg-slate-800 ring-2 ring-blue-500 overflow-hidden shadow-xl flex items-center justify-center shrink-0">
                        {getCharIconUrl(c) ? (
                          <img src={getCharIconUrl(c)} loading="lazy" decoding="async" alt={c.name} className="w-full h-full object-cover" />
                        ) : (
                          <span className="text-2xl text-slate-500 font-black">{c.name.slice(0,3)}</span>
                        )}
                      </div>
                      <div>
                        <h2 className="text-2xl sm:text-3xl font-black text-white mb-2">{c.name}</h2>
                        <span className="px-3 py-1 bg-slate-800 text-slate-300 font-bold rounded-lg ring-1 ring-white/10 text-xs sm:text-sm">
                          {t('character.rarity', { rarity: c.rarity || t('common.unknown') })}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center self-start sm:self-auto">
                      <Link
                        href={`/character/${selectedCharId}?tournaments=${selectedTournamentIds.join(',')}&registration_phase=${registrationPhase}`}
                        className="flex items-center space-x-1.5 px-4 py-2 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-xl text-sm font-bold ring-1 ring-blue-500/30 transition-all whitespace-nowrap"
                        onClick={() => setSelectedCharId(null)}
                      >
                        <span>📄</span>
                        <span>{t('action.viewFullDetails')}</span>
                      </Link>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-blue-500/10 p-6 rounded-2xl ring-1 ring-blue-500/20 flex flex-col items-center justify-center">
                      <p className="text-blue-400 text-sm font-bold mb-1">{t('stats.tournamentPicks')}</p>
                      <p className="text-3xl font-black text-blue-400">{t('stats.countTimes', { count: usageCount })}</p>
                    </div>
                    <div className="bg-emerald-500/10 p-6 rounded-2xl ring-1 ring-emerald-500/20 flex flex-col items-center justify-center">
                      <p className="text-emerald-400 text-sm font-bold mb-1">{t('stats.nonMirrorWinRate')}</p>
                      <p className="text-3xl font-black text-emerald-400">{winRate == null ? t("stats.noMatchRecords") : `${winRate}%`}</p>
                      <p className="text-xs text-emerald-500/60 mt-1">{t('stats.winsLosses', { wins: charWins, losses: charLosses })}</p>
                    </div>
                  </div>

                  {/* 編成順（配置ポジション分析） */}
                  {hasPositionStats && (
                    <div className="space-y-3">
                      <h3 className="font-bold text-white flex items-center space-x-2">
                        <span className="text-lg">📊</span>
                        <span>{t('character.positionTrend')}</span>
                      </h3>
                      <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-x-auto">
                        <table className="w-full text-center">
                          <thead>
                            <tr className="border-b border-white/10">
                              {[1,2,3,4,5].map(p => (
                                <th key={p} className="py-3 px-2 text-slate-400 font-black text-lg">{p}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {/* 配置回数（割合） */}
                            <tr className="border-b border-white/5">
                              {usageData.position_stats.map((ps: any) => (
                                <td key={ps.position} className="py-3 px-2">
                                  <span className="text-white font-bold text-lg">{ps.count}</span>
                                  <span className="text-slate-500 text-xs ml-0.5">{t('unit.times')}</span>
                                  <br />
                                  <span className="text-slate-400 text-xs">({ps.pct}%)</span>
                                </td>
                              ))}
                            </tr>
                            {/* ポジション別勝率 */}
                            <tr>
                              {usageData.position_stats.map((ps: any) => (
                                <td key={ps.position} className="py-3 px-2">
                                  {ps.total > 0 && ps.win_rate != null ? (
                                    <>
                                      <span className={`font-black text-lg ${ps.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                        {ps.win_rate}%
                                      </span>
                                      <br />
                                      <span className="text-slate-500 text-[10px]">{ps.wins}W {ps.total - ps.wins}L</span>
                                    </>
                                  ) : (
                                    <span className="text-slate-600 text-xs">-</span>
                                  )}
                                </td>
                              ))}
                            </tr>
                          </tbody>
                        </table>
                        <div className="px-4 py-2 bg-slate-900/50 border-t border-white/5 flex justify-between text-[10px] text-slate-500">
                          <span>{t('character.positionLegendTop')}</span>
                          <span>{t('character.positionLegendBottom')}</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 編成の配置傾向 */}
                  {hasTeamPositionStats && (
                    <div className="space-y-3">
                      <h3 className="font-bold text-white flex items-center space-x-2">
                        <span className="text-lg">📊</span>
                        <span>{t('character.teamPositionTrend')}</span>
                      </h3>
                      <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-x-auto">
                        <table className="w-full text-center">
                          <thead>
                            <tr className="border-b border-white/10 bg-slate-900/50">
                              <th className="py-2 px-2 text-slate-400 font-bold text-xs">{t('team.position')}</th>
                              <th className="py-2 px-2 text-slate-400 font-bold text-xs">{t('stats.usageCount')}</th>
                              <th className="py-2 px-2 text-slate-400 font-bold text-xs">{t('stats.winRate')}</th>
                              <th className="py-2 px-2 text-slate-400 font-bold text-xs">{t('teamMeaning.compositionBest')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {[1, 2, 3, 4, 5].map(pos => {
                              const ps = usageData.team_position_stats.find((p:any) => p.position === pos) || { count: 0, pct: 0, wins: 0, total: 0, win_rate: null, best_result: null };
                              return (
                                <tr key={pos} className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors">
                                  <td className="py-2 px-2 text-white font-bold text-sm">{t('team.positionValue', { position: pos })}</td>
                                  <td className="py-2 px-2">
                                    <span className="text-white font-bold text-sm">{ps.count}</span>
                                    <span className="text-slate-500 text-[10px] ml-0.5">{t('team.people')}</span>
                                    <br />
                                    <span className="text-slate-400 text-[10px]">({ps.pct}%)</span>
                                  </td>
                                  <td className="py-2 px-2">
                                    {ps.total > 0 && ps.win_rate != null ? (
                                      <>
                                        <span className={`font-bold text-sm ${ps.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                          {ps.win_rate}%
                                        </span>
                                        <br />
                                        <span className="text-slate-500 text-[10px]">{ps.wins}W {ps.total - ps.wins}L</span>
                                      </>
                                    ) : (
                                      <span className="text-slate-600 text-xs">{t('stats.noMatches')}</span>
                                    )}
                                  </td>
                                  <td className="py-2 px-2">
                                    {<CompositionBestResult team={ps}/>}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* よく一緒に編成されるキャラクター */}
                  <div className="space-y-3">
                    <h3 className="font-bold text-white flex items-center space-x-2">
                      <Users size={18} className="text-slate-400" />
                      <span>{t('character.synergy')}</span>
                    </h3>
                    <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-hidden divide-y divide-white/5">
                      {/* Burst 1 */}
                      <div className="flex flex-col md:flex-row">
                        <div className="md:w-24 bg-slate-800/80 p-3 flex items-center justify-center shrink-0 border-b md:border-b-0 md:border-r border-white/5">
                          <span className="font-bold text-slate-300 text-xs">BURST 1</span>
                        </div>
                        <div className="p-3 flex flex-wrap gap-2 flex-1">
                          {burst1Chars.map((ch: any) => (
                            <div key={ch.id} className="flex flex-col items-center space-y-1 p-1 rounded-lg hover:bg-slate-700/50 transition-colors">
                              <div className="w-10 h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 overflow-hidden flex items-center justify-center">
                                {getCharIconUrl(ch) ? (
                                  <img src={getCharIconUrl(ch)} loading="lazy" decoding="async" alt={ch.name} className="w-full h-full object-cover" />
                                ) : (
                                  <span className="text-[9px] text-slate-500 font-bold">{ch.name?.slice(0, 3)}</span>
                                )}
                              </div>
                              <span className="text-[9px] text-slate-300 w-12 truncate text-center" title={ch.name}>{ch.name}</span>
                              <span className="text-[9px] text-emerald-400 font-bold bg-emerald-400/10 px-1 rounded-full">
                                {t('stats.countTimes', { count: ch.synergyCount })} ({usageCount > 0 ? Math.round((ch.synergyCount / usageCount) * 100) : 0}%)
                              </span>
                            </div>
                          ))}
                          {burst1Chars.length === 0 && <span className="text-slate-500 text-xs p-2">{t('character.noMatch')}</span>}
                        </div>
                      </div>
                      {/* Burst 2 */}
                      <div className="flex flex-col md:flex-row">
                        <div className="md:w-24 bg-slate-800/80 p-3 flex items-center justify-center shrink-0 border-b md:border-b-0 md:border-r border-white/5">
                          <span className="font-bold text-slate-300 text-xs">BURST 2</span>
                        </div>
                        <div className="p-3 flex flex-wrap gap-2 flex-1">
                          {burst2Chars.map((ch: any) => (
                            <div key={ch.id} className="flex flex-col items-center space-y-1 p-1 rounded-lg hover:bg-slate-700/50 transition-colors">
                              <div className="w-10 h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 overflow-hidden flex items-center justify-center">
                                {getCharIconUrl(ch) ? (
                                  <img src={getCharIconUrl(ch)} loading="lazy" decoding="async" alt={ch.name} className="w-full h-full object-cover" />
                                ) : (
                                  <span className="text-[9px] text-slate-500 font-bold">{ch.name?.slice(0, 3)}</span>
                                )}
                              </div>
                              <span className="text-[9px] text-slate-300 w-12 truncate text-center" title={ch.name}>{ch.name}</span>
                              <span className="text-[9px] text-emerald-400 font-bold bg-emerald-400/10 px-1 rounded-full">
                                {t('stats.countTimes', { count: ch.synergyCount })} ({usageCount > 0 ? Math.round((ch.synergyCount / usageCount) * 100) : 0}%)
                              </span>
                            </div>
                          ))}
                          {burst2Chars.length === 0 && <span className="text-slate-500 text-xs p-2">{t('character.noMatch')}</span>}
                        </div>
                      </div>
                      {/* Burst 3 */}
                      <div className="flex flex-col md:flex-row">
                        <div className="md:w-24 bg-slate-800/80 p-3 flex items-center justify-center shrink-0 border-r border-white/5">
                          <span className="font-bold text-slate-300 text-xs">BURST 3</span>
                        </div>
                        <div className="p-3 flex flex-wrap gap-2 flex-1">
                          {burst3Chars.map((ch: any) => (
                            <div key={ch.id} className="flex flex-col items-center space-y-1 p-1 rounded-lg hover:bg-slate-700/50 transition-colors">
                              <div className="w-10 h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 overflow-hidden flex items-center justify-center">
                                {getCharIconUrl(ch) ? (
                                  <img src={getCharIconUrl(ch)} loading="lazy" decoding="async" alt={ch.name} className="w-full h-full object-cover" />
                                ) : (
                                  <span className="text-[9px] text-slate-500 font-bold">{ch.name?.slice(0, 3)}</span>
                                )}
                              </div>
                              <span className="text-[9px] text-slate-300 w-12 truncate text-center" title={ch.name}>{ch.name}</span>
                              <span className="text-[9px] text-emerald-400 font-bold bg-emerald-400/10 px-1 rounded-full">
                                {t('stats.countTimes', { count: ch.synergyCount })} ({usageCount > 0 ? Math.round((ch.synergyCount / usageCount) * 100) : 0}%)
                              </span>
                            </div>
                          ))}
                          {burst3Chars.length === 0 && <span className="text-slate-500 text-xs p-2">{t('character.noMatch')}</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <div className="space-y-4">
                    <h3 className="font-bold text-white flex items-center space-x-2">
                      <Users size={18} className="text-slate-400" />
                      <span>{t('character.relatedTeams')}</span>
                    </h3>

                    <div className="space-y-3">
                      {[...relatedTeams].sort((a: any, b: any) => {
                        const resultScores: Record<string, number> = {
                          "優勝": 1, "準優勝": 2, "ベスト4": 4,
                          "ベスト8": 8, "ベスト16": 16, "ベスト32": 32, "ベスト64": 64
                        };
                        const sa = resultScores[a.best_result] ?? 999;
                        const sb = resultScores[b.best_result] ?? 999;
                        return sa !== sb ? sa - sb : b.win_rate - a.win_rate; // 成績が同じなら勝率順
                      }).map((team: any, idx: number) => {
                        const teamResultColors: Record<string, string> = {
                          "優勝":   "bg-amber-400/20 text-amber-300 ring-amber-400/50",
                          "準優勝": "bg-slate-300/20 text-slate-200 ring-slate-300/50",
                          "ベスト4":  "bg-orange-500/20 text-orange-400 ring-orange-500/50",
                          "ベスト8":  "bg-blue-500/20 text-blue-400 ring-blue-500/50",
                          "ベスト16": "bg-purple-500/20 text-purple-400 ring-purple-500/50",
                          "ベスト32": "bg-slate-700/60 text-slate-400 ring-slate-600/50",
                          "ベスト64": "bg-slate-800/60 text-slate-500 ring-slate-700/50",
                        };
                        const teamResultClass = teamResultColors[team.best_result] ?? "bg-slate-800/60 text-slate-500 ring-slate-700/50";
                        return (
                          <div key={idx} onClick={() => handleTeamClick(team.canonical_id, team)} className="flex flex-col bg-slate-800/50 hover:bg-slate-700/60 cursor-pointer transition-colors p-4 rounded-xl ring-1 ring-white/5 space-y-3">
                            {/* 編成アイコン行 */}
                            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                              <div><TeamDisplay charIds={team.character_ids} allCharacters={allCharacters} /><TeamRegistrationUsage team={team}/></div>
                              <div className="flex items-center space-x-2 shrink-0 ml-4">
                                <TeamBestResults team={team}/>
                                <span className="text-slate-400 font-bold bg-slate-900 px-2 py-0.5 rounded-lg ring-1 ring-white/10 text-xs">
                                  {t('stats.teamPick', { count: team.count })}
                                </span>
                              </div>
                            </div>
                            {/* 勝率・勝敗行 */}
                            {team.total_matches > 0 && (
                              <div className="flex items-center space-x-4 pt-2 border-t border-white/5">
                                <div className="flex items-center space-x-2">
                                  <span className="text-[10px] text-slate-500 font-bold uppercase">{t('stats.winRate')}</span>
                                  <span className={`text-lg font-black ${team.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                    {team.win_rate}%
                                  </span>
                                </div>
                                <div className="h-4 w-px bg-white/10"></div>
                                <div className="flex items-center space-x-2 text-xs font-bold">
                                  <span className="text-emerald-400">{t('stats.winsLosses', { wins: team.win_count, losses: team.total_matches - team.win_count })}</span>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {relatedTeams.length === 0 && (
                        <p className="text-slate-500 text-sm text-center py-4">{t('common.noData')}</p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}
    </main>
  );
}

// useSearchParams を使用するため Suspense でラップが必要（Next.js 15 要件）
export default function Dashboard() {
  const { t } = useI18n();
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#0a0f1e] flex items-center justify-center">
          <div className="text-center space-y-4">
            <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-slate-400 font-bold">{t('common.loading')}</p>
          </div>
        </main>
      }
    >
      <DashboardContent />
    </Suspense>
  );
}
