"use client";
export const dynamic = 'force-dynamic';
import { useState, useEffect, Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ChevronDown, ChevronLeft, SlidersHorizontal, TrendingUp, Users, Swords, Search, X, Trophy, User as UserIcon, Globe } from "lucide-react";
import Link from "next/link";
import PaginatedTeamList from "../components/PaginatedTeamList";
import { useAuth } from "../context/AuthContext";

const SERVER_LABELS: Record<string, string> = {
  KR: "韓国（KR）",
  JP: "日本（JP）",
  GLOBAL: "グローバル（ヨーロッパ）",
  NA: "北米",
  SEA: "東南アジア",
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
  const { user } = useAuth();
  const searchParams = useSearchParams();

  // URLクエリパラメータから初期タブ・編成を復元（キャラ詳細ページからの遷移用）
  const requestedTab = searchParams.get("tab") as DashboardTab | null;
  const initialTab = requestedTab && PUBLIC_TABS.has(requestedTab)
    ? requestedTab
    : "team_winrate";
  const initialTeam = searchParams.get("team");

  const [tournament, setTournament] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [matchups, setMatchups] = useState<any[]>([]);
  const [allCharacters, setAllCharacters] = useState<any[]>([]);
  const [bracketData, setBracketData] = useState<any>(null);
  const [myPlayerDetails, setMyPlayerDetails] = useState<any>(null);
  const [best8Data, setBest8Data] = useState<any[]>([]);
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
  const [isPositionStatsOpen, setIsPositionStatsOpen] = useState(true);
  const [isAdoptedPlayersOpen, setIsAdoptedPlayersOpen] = useState(true);
  const [matchupFilterResult, setMatchupFilterResult] = useState<"ALL" | "WIN" | "LOSE">("ALL");
  const [matchupFilterSide, setMatchupFilterSide] = useState<"ALL" | "ATTACK" | "DEFENSE">("ALL");
  const [matchupFilterStage, setMatchupFilterStage] = useState<string>("ALL");

  // For search
  const [searchChars, setSearchChars] = useState<number[]>([]);
  const [filterRarity, setFilterRarity] = useState<string>("");
  const [filterManufacturer, setFilterManufacturer] = useState<string>("");
  const [filterBurst, setFilterBurst] = useState<string>("");
  const [filterElement, setFilterElement] = useState<string>("");
  const [filterWeapon, setFilterWeapon] = useState<string>("");

  // For winrate filters
  const [winrateMinMatches, setWinrateMinMatches] = useState<number>(1);
  const [winrateBurstPhase, setWinrateBurstPhase] = useState<string>("");
  const [winrateWeapon, setWinrateWeapon] = useState<string>("");
  const [winrateElement, setWinrateElement] = useState<string>("");
  const [winrateManufacturer, setWinrateManufacturer] = useState<string>("");

  // For team filters
  const [teamMinMatches, setTeamMinMatches] = useState<number>(10);
  const [teamBestResult, setTeamBestResult] = useState<string>("");
    const [teamMinWinRate, setTeamMinWinRate] = useState<number>(0);
  
  // For Character Modal
  const [selectedCharId, setSelectedCharId] = useState<number | null>(null);
  const [selectedCharacterDetail, setSelectedCharacterDetail] = useState<any>(null);
  const [selectedCharacterDetailLoading, setSelectedCharacterDetailLoading] = useState(false);

  // For My Dashboard Tab Search
  const [seedSearchQuery, setSeedSearchQuery] = useState<string>("");

  const handleTeamClick = (canonicalId: string) => {
    if (!canonicalId) return;
    setSelectedTeam(canonicalId);
    setActiveTab("matchups");
    setSelectedCharId(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
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
        if (!res.ok) return;
        const data: any[] = await res.json();
        if (!Array.isArray(data)) return;
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
        setLoading(false);
      }
    };
    fetchTournaments();
  }, [isFirstLoad, user?.game_start_date]);

  const selectedChampionshipId = allTournaments.find(t => t.play_server === filterServer && t.season === filterSeason)?.championship_id;

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
  }, [filterServer, filterSeason, isAllTournamentsSelected, selectedSpecificTournamentIds, allTournaments]);

  // フィルタ状態を localStorage に保存
  useEffect(() => {
    if (isFirstLoad || allTournaments.length === 0) return;
    localStorage.setItem('nikke_filter_server', filterServer);
    localStorage.setItem('nikke_filter_season', filterSeason);
    localStorage.setItem('nikke_filter_is_all', isAllTournamentsSelected.toString());
    localStorage.setItem('nikke_filter_specific_ids', JSON.stringify(selectedSpecificTournamentIds));
  }, [filterServer, filterSeason, isAllTournamentsSelected, selectedSpecificTournamentIds, allTournaments, isFirstLoad]);

  const [allBracketData, setAllBracketData] = useState<any[]>([]);

  useEffect(() => {
    if (!selectedCharId || selectedTournamentIds.length === 0) {
      setSelectedCharacterDetail(null);
      return;
    }

    const fetchCharacterDetail = async () => {
      setSelectedCharacterDetailLoading(true);
      try {
        const res = await fetch("/api/dashboard/cross-tournament/character-detail", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            character_id: selectedCharId,
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
        setSelectedCharacterDetail(data);
      } catch (e) {
        console.error("failed to fetch selected character detail", e);
      } finally {
        setSelectedCharacterDetailLoading(false);
      }
    };

    fetchCharacterDetail();
  }, [selectedCharId, selectedTournamentIds, filterServer, selectedChampionshipId]);

  useEffect(() => {
    if (isFirstLoad) return;
    // allTournamentsにデータがあるのにフィルタ後0件の場合もローディング終了
    if (allTournaments.length > 0 && selectedTournamentIds.length === 0) {
      setStats(null);
      setMatchups([]);
      setAllBracketData([]);
      setLoading(false);
      return;
    }
    if (selectedTournamentIds.length === 0) return;

    const fetchData = async () => {
      setLoading(true);
      try {
        const timestamp = Date.now();
        
        // 1. 全キャラクター情報取得
        const charsRes = await fetch(`/api/characters?t=${timestamp}`, { cache: 'no-store' });
        if (charsRes.ok) {
          setAllCharacters(await charsRes.json());
        }

        // 2. 選択された大会の BracketData などを並列取得
        const brackets = await Promise.all(
          selectedTournamentIds.map(async (id) => {
            const res = await fetch(`/api/tournaments/${id}/bracket?t=${timestamp}`);
            const data = res.ok ? await res.json() : null;
            return { tournamentId: id, data };
          })
        );
        setAllBracketData(brackets);

        // ※ 複数大会選択時は best8Data 等はどう扱うか？ 今回は cross-tournament stats に集約
        // myPlayerDetails も全大会分取る必要はない。ブラケットデータがあればシードからプレイヤーを探せる。

        // 3. 横断分析APIの呼び出し
        if (
          selectedTournamentIds.length === 0 ||
          !filterServer ||
          !filterSeason ||
          !selectedChampionshipId
        ) {
          return;
        }

        const reqBody = { 
          tournament_ids: selectedTournamentIds,
          play_server: filterServer,
          championship_id: selectedChampionshipId
        };
        
        const statsRes = await fetch(`/api/dashboard/cross-tournament/stats?t=${timestamp}`, {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(reqBody)
          });
        
        if (statsRes.ok) {
          const statsData = await statsRes.json();
          setStats(statsData);
          
          if (statsData.team_usage && statsData.team_usage.length > 0 && !selectedTeam) {
            setSelectedTeam(statsData.team_usage[0].canonical_id);
          }
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [selectedTournamentIds, isFirstLoad]);

  useEffect(() => {
    if (activeTab !== "matchups" && activeTab !== "team_winrate") return;
    if (matchups.length > 0 || selectedTournamentIds.length === 0) return;

    const fetchMatchups = async () => {
      try {
        if (
          selectedTournamentIds.length === 0 ||
          !filterServer ||
          !filterSeason ||
          !selectedChampionshipId
        ) {
          return;
        }

        const reqBody = { 
          tournament_ids: selectedTournamentIds,
          play_server: filterServer,
          championship_id: selectedChampionshipId
        };
        const res = await fetch(`/api/dashboard/cross-tournament/matchups?t=${Date.now()}`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(reqBody)
        });
        if (!res.ok) return;
        const data = await res.json();
        setMatchups(data.matchups || data);
      } catch(e) {
        console.error(e);
      }
    };
    fetchMatchups();
  }, [activeTab, selectedTournamentIds, matchups.length]);

  if (loading) return (
    <div className="flex h-screen items-center justify-center">
      <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );

  if (allTournaments.length === 0) {
    return (
      <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 font-sans">
        <header className="sticky top-0 z-40 w-full border-b border-white/10 bg-slate-900/80 backdrop-blur-md">
          <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="text-xl font-black tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-400">
                NIKKE ARENA ANALYZER
              </span>
            </div>
            <div className="flex items-center space-x-4">
              <a href="/tournaments/manage" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-bold transition-all shadow-lg shadow-blue-500/20">
                大会データ登録
              </a>
            </div>
          </div>
        </header>
        
        <main className="flex-1 max-w-4xl mx-auto px-4 py-16 flex flex-col items-center justify-center text-center">
          <div className="w-24 h-24 rounded-3xl bg-slate-900 border border-white/10 flex items-center justify-center mb-8 shadow-2xl">
            <span className="text-4xl">📊</span>
          </div>
          <h1 className="text-3xl font-black mb-4 tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
            にけあり！へようこそ
          </h1>
          <p className="text-slate-400 text-base max-w-md mb-8 leading-relaxed">
            現在、システムに大会データが登録されていません。<br />
            まずは右上の「大会データ登録」ボタンから、対戦結果データをインポートしてください。
          </p>
          <a href="/tournaments/manage" className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold transition-all shadow-xl shadow-blue-500/20">
            <span>大会データ登録へ移動</span>
          </a>
        </main>
      </div>
    );
  }

  // Helper to render a team
  const TeamDisplay = ({ charIds }: { charIds: number[] }) => {
    const displayChars = charIds.map(cid => allCharacters.find(c => c.id === cid)).filter(Boolean);
    return (
      <div className="flex space-x-2">
        {displayChars.map((c: any, i: number) => {
          if (c.id === 9999) {
            return (
              <div key={i} className="flex flex-col items-center space-y-1 opacity-50">
                <div className="w-10 h-10 rounded-lg bg-slate-800/50 ring-1 ring-white/5 overflow-hidden flex items-center justify-center">
                  <div className="text-slate-600 text-xs">-</div>
                </div>
                <span className="text-[9px] text-slate-500 w-10 truncate text-center" title="空枠">空枠</span>
              </div>
            );
          }
          return (
            <div key={i} className="flex flex-col items-center space-y-1 cursor-pointer group" onClick={(e) => { e.stopPropagation(); setSelectedCharId(c.id); }}>
              <div className="w-10 h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 group-hover:ring-blue-500 overflow-hidden flex items-center justify-center transition-all">
                {c?.is_template_available ? (
                  <img src={`/api/char-icon/${c.id}.png`} loading="lazy" decoding="async" alt={c?.name || "不明"} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-[10px] text-slate-500 font-bold leading-tight text-center">{c?.name?.slice(0, 3) || "不明"}</span>
                )}
              </div>
              <span className="text-[9px] text-slate-400 w-10 truncate text-center" title={c?.name || "不明"}>{c?.name || "不明"}</span>
            </div>
          );
        })}
      </div>
    );
  };

  // --- Matchups logic ---
  const teamMatchups = matchups.filter(m => m.canonical_attacker === selectedTeam || m.canonical_defender === selectedTeam);
  let totalWins = 0, totalLosses = 0;
  let attackWins = 0, attackLosses = 0;
  let defenseWins = 0, defenseLosses = 0;
  const matchupDetails: any[] = [];

  teamMatchups.forEach(m => {
    const isAttacker = m.canonical_attacker === selectedTeam;
    const isWin = m.winner_is_attacker ? isAttacker : !isAttacker;
    if (isWin) totalWins++; else totalLosses++;
    if (isAttacker) { if (isWin) attackWins++; else attackLosses++; }
    else { if (isWin) defenseWins++; else defenseLosses++; }
    matchupDetails.push({ 
      opponent: isAttacker ? m.defender_team : m.attacker_team, 
      opponentCanonical: isAttacker ? m.canonical_defender : m.canonical_attacker,
      isAttacker, 
      isWin, 
      stage: m.stage,
      tournamentName: m.tournament_name,
      attackerName: m.attacker_name,
      defenderName: m.defender_name
    });
  });

  // --- My Dashboard logic ---
  const mySeed = selectedSeed;
  let myPlayer: any = null;
  let myTournamentResult = "グループ1回戦出場 (Best 64)";
  
  if (bracketData && bracketData.groups) {
     // 1. Search in groups
     bracketData.groups.forEach((g: any, idx: number) => {
        const found = g.players.find((p:any) => (p.original_seed || p.seed) === mySeed && p.id !== null);
        if (found) {
           myPlayer = found;
           
           const reached_qf = g.qf_winners?.includes(myPlayer.id);
           const reached_sf = g.sf_winners?.includes(myPlayer.id);
           const reached_f = g.winner === myPlayer.id;
           
           const qf_played = g.qf_winners?.length > 0;
           const sf_played = g.sf_winners?.length > 0;
           const f_played = g.winner !== null;
           
           if (reached_f) {
              myTournamentResult = "グループ優勝 (Best 8 進出)";
           } else if (reached_sf) {
              if (f_played) myTournamentResult = "グループ決勝敗退 (Best 16)";
              else myTournamentResult = "グループ決勝進出 (Best 16)";
           } else if (reached_qf) {
              if (sf_played) myTournamentResult = "グループ準決勝敗退 (Best 32)";
              else myTournamentResult = "グループ準決勝進出 (Best 32)";
           } else {
              if (qf_played && !reached_qf) {
                 // To be absolutely precise we could check specific matchups, but generally if qf_winners has this group's winners,
                 // and the player is not in it, they lost.
                 myTournamentResult = "グループ1回戦敗退 (Best 64)";
              } else {
                 myTournamentResult = "グループ1回戦出場 (Best 64)";
              }
           }
        }
     });
     
     // 2. Search in champion finals if they advanced
     if (myPlayer && bracketData.champion_finals) {
        const cf = bracketData.champion_finals;
        if (cf.players.find((p:any) => p.id === myPlayer.id)) {
           const reached_cf_sf = cf.qf_winners?.includes(myPlayer.id); // Best 4
           const reached_cf_f = cf.sf_winners?.includes(myPlayer.id); // Final
           const is_champ = cf.winner === myPlayer.id;
           
           const cf_qf_played = cf.qf_winners?.length > 0;
           const cf_sf_played = cf.sf_winners?.length > 0;
           const cf_f_played = cf.winner !== null;

           if (is_champ) {
               myTournamentResult = "🏆 チャンピオン 🏆";
           } else if (reached_cf_f) {
               if (cf_f_played) myTournamentResult = "準優勝 (2位)";
               else myTournamentResult = "決勝進出 (2位以上確定)";
           } else if (reached_cf_sf) {
               if (cf_sf_played) myTournamentResult = "ベスト4";
               else myTournamentResult = "準決勝進出 (Best 4)";
           } else {
               if (cf_qf_played && !reached_cf_sf) {
                   myTournamentResult = "ベスト8敗退";
               } else {
                   myTournamentResult = "チャンピオン対抗戦出場 (Best 8)";
               }
           }
        }
     }
  }

  const myDecks = myPlayerDetails?.decks || [];

  const seasons = Array.from(new Set(allTournaments.map(t => t.season || "β30")));
  const playServers = Object.keys(SERVER_LABELS);
  const availableServers = new Set(allTournaments.map(t => t.play_server).filter(Boolean));
  const gameStartDates = Array.from(new Set(
    allTournaments.map(t => t.provider_game_start_date).filter(Boolean)
  )).sort() as string[];

  return (
    <main className="p-3 sm:p-4 md:p-8 max-w-[1400px] mx-auto space-y-4 md:space-y-8 pb-24">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between space-y-4 md:space-y-0 mb-2 md:mb-8 border-b border-white/10 pb-4 md:pb-6">
        <div className="flex min-w-0 items-center space-x-3 md:space-x-4">
          <div className="shrink-0 p-2.5 md:p-3 bg-gradient-to-br from-blue-500 to-emerald-600 rounded-xl md:rounded-2xl shadow-lg shadow-blue-500/20">
            <Trophy className="h-6 w-6 text-white md:h-8 md:w-8" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">
              NIKKE Arena Analyzer
            </h1>
            <p className="text-slate-400 text-xs md:text-sm mt-1 leading-relaxed">にけあり！ ～チャンアリをもっと楽しむためのファンサイト～</p>
          </div>
        </div>
        
      </div>

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
              <span className="block text-sm font-bold text-slate-100">分析対象フィルタ</span>
              <span className="block truncate text-xs text-slate-400">
                分析対象: {SERVER_LABELS[filterServer] || filterServer} / {filterSeason} / 
                {isAllTournamentsSelected ? `全${allTournaments.filter(t => t.play_server === filterServer && (t.season || "β30") === filterSeason).length}大会` : `${selectedTournamentIds.length}大会`}
              </span>
            </span>
            <span className="shrink-0 rounded bg-blue-500/15 px-2 py-1 text-xs font-bold text-blue-300">
              {selectedTournamentIds.length}大会
            </span>
            <ChevronDown className={`h-5 w-5 shrink-0 text-slate-400 transition-transform ${isMobileFiltersOpen ? "rotate-180" : ""}`} />
          </button>

          <div
            id="mobile-dashboard-filters"
            className={`${isMobileFiltersOpen ? "block" : "hidden"} bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-4 sm:p-5 xl:p-6 rounded-lg sm:rounded-xl xl:rounded-3xl shadow-2xl xl:sticky xl:top-6 xl:block`}
          >
            <h3 className="hidden text-lg font-bold text-slate-100 mb-6 xl:flex items-center space-x-2">
              <Search size={18} className="text-blue-400" />
              <span>分析対象フィルタ</span>
            </h3>
            
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 xl:block xl:space-y-6">
              <div>
                <div className="text-xs font-bold text-slate-500 mb-3 uppercase tracking-wider">プレイサーバー</div>
                <select 
                  value={filterServer}
                  onChange={(e) => {
                    const newServer = e.target.value;
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
                      {SERVER_LABELS[server] || server}
                    </option>
                  ))}
                </select>
              </div>

              <div className="hidden h-px w-full bg-white/10 xl:block"></div>

              <div>
                <div className="text-xs font-bold text-slate-500 mb-3 uppercase tracking-wider">開催期間 (シーズン)</div>
                <select
                  value={filterSeason}
                  onChange={(e) => {
                    setFilterSeason(e.target.value);
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
                <div className="text-xs font-bold text-slate-500 mb-3 uppercase tracking-wider">対象大会</div>
                <div className="flex items-center space-x-4 mb-3 px-1">
                  <label className="flex items-center space-x-2 cursor-pointer group">
                    <input type="radio" 
                      checked={isAllTournamentsSelected} 
                      onChange={() => setIsAllTournamentsSelected(true)}
                      className="w-4 h-4 text-blue-500 bg-slate-800 border-white/20 focus:ring-blue-500 focus:ring-offset-slate-900" 
                    />
                    <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">すべて</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer group">
                    <input type="radio" 
                      checked={!isAllTournamentsSelected} 
                      onChange={() => setIsAllTournamentsSelected(false)}
                      className="w-4 h-4 text-blue-500 bg-slate-800 border-white/20 focus:ring-blue-500 focus:ring-offset-slate-900" 
                    />
                    <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">個別に選ぶ</span>
                  </label>
                </div>
                
                {!isAllTournamentsSelected && (
                  <div className="space-y-2.5 max-h-48 overflow-y-auto pr-2 custom-scrollbar mt-2 bg-slate-950/30 p-2 rounded-lg ring-1 ring-white/5">
                    {allTournaments
                      .filter(t => (t.play_server || "") === filterServer && (t.season || "β30") === filterSeason)
                      .sort((a, b) => new Date(a.provider_game_start_date || 0).getTime() - new Date(b.provider_game_start_date || 0).getTime())
                      .map(t => (
                      <label key={t.id} className="flex items-center space-x-3 cursor-pointer group">
                        <input type="checkbox" checked={selectedSpecificTournamentIds.includes(t.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedSpecificTournamentIds([...selectedSpecificTournamentIds, t.id]);
                            } else {
                              setSelectedSpecificTournamentIds(selectedSpecificTournamentIds.filter(id => id !== t.id));
                            }
                          }}
                          className="w-4 h-4 rounded bg-slate-800 border-white/20 text-emerald-500 focus:ring-emerald-500 focus:ring-offset-slate-900 transition-colors cursor-pointer"
                        />
                        <span className="text-xs font-medium text-slate-300 group-hover:text-white transition-colors truncate">
                          {t.provider_game_start_date ? `${t.provider_game_start_date}開始` : (t.name || `大会 #${t.id}`)}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
            
            <div className="hidden mt-8 p-4 rounded-xl bg-blue-500/10 ring-1 ring-blue-500/20 xl:block">
              <div className="text-xs text-blue-400 font-bold mb-1">対象大会数</div>
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
              <span>編成別勝率</span>
            </button>
            <button 
              onClick={() => setActiveTab("matchups")}
              className={`flex snap-start items-center space-x-1.5 px-3 py-2.5 text-xs md:space-x-2 md:px-6 md:py-3 md:text-base rounded-md md:rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "matchups" ? "bg-purple-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
            >
              <Swords size={18} />
              <span>編成詳細</span>
            </button>

            <button 
              onClick={() => setActiveTab("search")}
              className={`flex snap-start items-center space-x-1.5 px-3 py-2.5 text-xs md:space-x-2 md:px-6 md:py-3 md:text-base rounded-md md:rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "search" ? "bg-emerald-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
            >
              <Search size={18} />
              <span>シナジー逆引き検索</span>
            </button>
            <button
              onClick={() => setActiveTab("overview")}
              className={`flex snap-start items-center space-x-1.5 px-3 py-2.5 text-xs md:space-x-2 md:px-6 md:py-3 md:text-base rounded-md md:rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "overview" ? "bg-blue-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
            >
              <TrendingUp size={18} />
              <span>トレンド分析</span>
            </button>
          </div>
          </div>

          {/* Content */}
          <div className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-3 sm:p-4 md:p-8 rounded-lg sm:rounded-xl md:rounded-3xl shadow-2xl min-h-[500px]">
        

        {/* OVERVIEW TAB */}
        {activeTab === "overview" && (
           <div className="space-y-12 animate-in fade-in zoom-in-95 duration-300">
            <section>
              <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
                <Users className="text-blue-400" />
                <span>キャラクター採用率ランキング</span>
              </h2>
              <div className="overflow-x-auto rounded-xl ring-1 ring-white/10 shadow-2xl bg-slate-900/50">
                {(() => {
                  // 採用数でグループ化
                  const grouped: { count: number; entries: any[] }[] = [];
                  if (!stats) return <div className="py-12 text-center text-slate-500">データ読み込み中...</div>;
                  const sorted = [...(stats.character_usage ?? [])].sort((a: any, b: any) => b.count - a.count);
                  sorted.forEach((entry: any) => {
                    const last = grouped[grouped.length - 1];
                    if (last && last.count === entry.count) {
                      last.entries.push(entry);
                    } else {
                      grouped.push({ count: entry.count, entries: [entry] });
                    }
                  });

                  return (
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="bg-slate-800/80 text-slate-400 text-sm border-b border-white/10">
                          <th className="p-4 font-medium text-center w-16">順位</th>
                          <th className="p-4 font-medium text-center w-24">採用数</th>
                          <th className="p-4 font-medium">キャラクター</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {grouped.map((group, gIdx) => {
                          // 順位計算（同着を考慮）
                          const rank = sorted.findIndex(e => e.count === group.count) + 1;
                          return (
                            <tr key={gIdx} className="hover:bg-white/5 transition-colors">
                              <td className="p-4 text-center align-top">
                                <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full font-black ${
                                  rank === 1 ? "bg-yellow-500/20 text-yellow-500 ring-1 ring-yellow-500/50" :
                                  rank === 2 ? "bg-slate-300/20 text-slate-300 ring-1 ring-slate-300/50" :
                                  rank === 3 ? "bg-amber-600/20 text-amber-500 ring-1 ring-amber-600/50" :
                                  "text-slate-500"
                                }`}>
                                  {rank}
                                </span>
                              </td>
                              <td className="p-4 text-center align-top">
                                <span className="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">
                                  {group.count}
                                </span>
                              </td>
                              <td className="p-4">
                                <div className="flex flex-wrap gap-2">
                                  {group.entries.map((entry: any) => {
                                    const c = allCharacters.find(char => char.id === entry.id) || entry;
                                    return (
                                      <button
                                        key={c.id}
                                        onClick={() => setSelectedCharId(c.id)}
                                        title={c.name}
                                        className="flex items-center space-x-1.5 bg-slate-800/80 hover:bg-slate-700 px-2 py-1.5 rounded-lg ring-1 ring-white/10 hover:ring-blue-500/50 transition-all group/char"
                                      >
                                        <div className="w-8 h-8 rounded-md bg-slate-700 ring-1 ring-white/10 overflow-hidden flex items-center justify-center shrink-0 group-hover/char:ring-blue-500 transition-all">
                                          {c?.is_template_available ? (
                                            <img src={`/api/char-icon/${c.id}.png`} loading="lazy" decoding="async" alt={c.name} className="w-full h-full object-cover" />
                                          ) : (
                                            <span className="text-[8px] text-slate-500 font-bold">{c.name.slice(0,2)}</span>
                                          )}
                                        </div>
                                        <span className="text-xs font-bold text-slate-300 group-hover/char:text-blue-400 transition-colors whitespace-nowrap">
                                          {c.name}
                                        </span>
                                      </button>
                                    );
                                  })}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                        {(stats?.character_usage?.length ?? 0) === 0 && (
                          <tr>
                            <td colSpan={3} className="p-8 text-center text-slate-500">データがありません</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  );
                })()}
              </div>
            </section>
            <section>
              <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
                <Users className="text-emerald-400" />
                <span>編成（5名組み合わせ）使用率ランキング</span>
              </h2>
              <div className="overflow-x-auto rounded-xl ring-1 ring-white/10 shadow-2xl bg-slate-900/50">
                <table className="w-full text-left border-collapse min-w-[900px]">
                  <thead>
                    <tr className="bg-slate-800/80 text-slate-400 text-sm border-b border-white/10">
                      <th className="p-4 font-medium text-center w-16">順位</th>
                      <th className="p-4 font-medium">編成</th>
                      <th className="p-4 font-medium text-center w-32">最終成績</th>
                      <th className="p-4 font-medium text-right w-28">勝率</th>
                      <th className="p-4 font-medium text-right w-40">採用数</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {(stats?.team_usage ?? []).slice(0, 15).map((team: any, idx: number) => {
                      const resultColors: Record<string, string> = {
                        "優勝":   "bg-amber-400/20 text-amber-300 ring-amber-400/50",
                        "準優勝": "bg-slate-300/20 text-slate-200 ring-slate-300/50",
                        "ベスト4":  "bg-orange-500/20 text-orange-400 ring-orange-500/50",
                        "ベスト8":  "bg-blue-500/20 text-blue-400 ring-blue-500/50",
                        "ベスト16": "bg-purple-500/20 text-purple-400 ring-purple-500/50",
                        "ベスト32": "bg-slate-700/60 text-slate-400 ring-slate-600/50",
                        "ベスト64": "bg-slate-800/60 text-slate-500 ring-slate-700/50",
                      };
                      const resultClass = resultColors[team.best_result] ?? "bg-slate-800/60 text-slate-500 ring-slate-700/50";
                      // 64人参加を前提とした採用率の計算
                      const totalPlayers = 64;
                      const adoptionPct = Math.round((team.count / totalPlayers) * 100);
                      return (
                        <tr key={idx} className="hover:bg-white/5 transition-colors cursor-pointer group" onClick={() => handleTeamClick(team.canonical_id)}>
                          <td className="p-4 text-center">
                            <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full font-black ${
                              idx + 1 === 1 ? "bg-yellow-500/20 text-yellow-500 ring-1 ring-yellow-500/50" :
                              idx + 1 === 2 ? "bg-slate-300/20 text-slate-300 ring-1 ring-slate-300/50" :
                              idx + 1 === 3 ? "bg-amber-600/20 text-amber-500 ring-1 ring-amber-600/50" :
                              "text-slate-500"
                            }`}>
                              {idx + 1}
                            </span>
                          </td>
                          <td className="p-4">
                            <TeamDisplay charIds={team.character_ids} />
                          </td>
                          <td className="p-4 text-center">
                            {team.best_result ? (
                              <span className={`inline-block px-3 py-1 text-xs font-bold rounded-full ring-1 ${resultClass}`}>
                                {team.best_result}
                              </span>
                            ) : (
                              <span className="text-slate-600 text-xs">-</span>
                            )}
                          </td>
                          <td className="p-4 text-right">
                            {team.total_matches > 0 ? (
                              <div className="flex flex-col items-end">
                                <span className={`text-lg font-black ${team.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                  {team.win_rate}%
                                </span>
                                <span className="text-[10px] text-slate-500 font-bold">
                                  {team.win_count}W {team.total_matches - team.win_count}L
                                </span>
                              </div>
                            ) : (
                              <span className="text-slate-600 text-xs">対戦なし</span>
                            )}
                          </td>
                          <td className="p-4 text-right">
                            <div className="flex flex-col items-end">
                              <span className="text-lg font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">
                                {team.count}
                              </span>
                              <span className="text-[10px] text-slate-500 font-bold">
                                {totalPlayers}人中 ({adoptionPct}%)
                              </span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {(stats?.team_usage?.length ?? 0) === 0 && (
                      <tr>
                        <td colSpan={5} className="p-8 text-center text-slate-500">データがありません</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}



        {/* TEAM WINRATE TAB */}
        {activeTab === "team_winrate" && (
           <div className="space-y-12 animate-in fade-in zoom-in-95 duration-300">
            <section>
              <div className="flex flex-col md:flex-row md:items-center justify-between mb-6 space-y-4 md:space-y-0">
                <h2 className="text-xl font-bold text-white flex items-center space-x-2">
                  <Trophy className="text-emerald-400" />
                  <span>編成別勝率ランキング</span>
                </h2>
                
                {/* 編成フィルタコントロール群 */}
                <div className="flex flex-wrap gap-2 items-center">
                  <select
                    value={teamMinMatches}
                    onChange={(e) => setTeamMinMatches(Number(e.target.value))}
                    className="bg-slate-800 text-slate-200 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value={1}>対戦数：1戦以上</option>
                    <option value={10}>対戦数：10戦以上</option>
                    <option value={30}>対戦数：30戦以上</option>
                    <option value={50}>対戦数：50戦以上</option>
                  </select>

                  <select
                    value={teamMinWinRate}
                    onChange={(e) => setTeamMinWinRate(Number(e.target.value))}
                    className="bg-slate-800 text-slate-200 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value={0}>勝率：指定なし</option>
                    <option value={50}>勝率：50%以上</option>
                    <option value={60}>勝率：60%以上</option>
                    <option value={70}>勝率：70%以上</option>
                    <option value={80}>勝率：80%以上</option>
                  </select>

                  <select
                    value={teamBestResult}
                    onChange={(e) => setTeamBestResult(e.target.value)}
                    className="bg-slate-800 text-slate-200 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="">最終成績：すべて</option>
                    <option value="優勝">最終成績：優勝のみ</option>
                    <option value="準優勝">最終成績：準優勝以上</option>
                    <option value="ベスト4">最終成績：ベスト4以上</option>
                    <option value="ベスト8">最終成績：ベスト8以上</option>
                    <option value="ベスト16">最終成績：ベスト16以上</option>
                    <option value="ベスト32">最終成績：ベスト32以上</option>
                  </select>
                </div>
              </div>

              <div className="space-y-3">
                <PaginatedTeamList 
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
                  bestResult={teamBestResult}
                />
              </div>
            </section>
          </div>
        )}

        {/* MATCHUPS TAB */}
        {activeTab === "matchups" && (
          <div className="space-y-8 animate-in fade-in zoom-in-95 duration-300">
            <div className="bg-purple-500/10 p-6 rounded-2xl ring-1 ring-purple-500/20">
              <label className="block text-sm font-bold text-purple-400 mb-3">分析する編成を選択</label>
              <select 
                className="w-full bg-slate-900 border border-purple-500/30 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500 mb-4"
                value={selectedTeam}
                onChange={e => setSelectedTeam(e.target.value)}
              >
                {(stats?.team_usage ?? []).map((team: any, idx: number) => (
                  <option key={idx} value={team.canonical_id}>
                    [{team.count}回採用] {team.characters.map((c:any) => c.id === 9999 ? '空枠' : c.name).join(" / ")}
                  </option>
                ))}
              </select>
              
              {selectedTeam && (
                <div className="pt-4 border-t border-purple-500/20 flex flex-col space-y-2">
                  <span className="text-xs font-bold text-purple-400">選択中の編成:</span>
                  <TeamDisplay charIds={(stats?.team_usage ?? []).find((t:any) => t.canonical_id === selectedTeam)?.character_ids || []} />
                </div>
              )}
            </div>

            {selectedTeam ? (
              <div className="grid md:grid-cols-3 gap-6">
                <div className="bg-slate-800/50 p-6 rounded-2xl ring-1 ring-white/5 flex flex-col items-center justify-center">
                  <p className="text-slate-400 text-sm mb-2">総合勝率</p>
                  <p className="text-4xl font-black text-white">
                    {totalWins + totalLosses > 0 ? Math.round((totalWins / (totalWins + totalLosses)) * 100) : 0}%
                  </p>
                  <p className="text-sm text-slate-500 mt-2">{totalWins}勝 {totalLosses}敗</p>
                </div>
                <div className="bg-blue-500/10 p-6 rounded-2xl ring-1 ring-blue-500/20 flex flex-col items-center justify-center">
                  <p className="text-blue-400 text-sm mb-2">攻撃側 (自分から) 勝率</p>
                  <p className="text-4xl font-black text-blue-400">
                    {attackWins + attackLosses > 0 ? Math.round((attackWins / (attackWins + attackLosses)) * 100) : 0}%
                  </p>
                  <p className="text-sm text-blue-500/60 mt-2">{attackWins}勝 {attackLosses}敗</p>
                </div>
                <div className="bg-red-500/10 p-6 rounded-2xl ring-1 ring-red-500/20 flex flex-col items-center justify-center">
                  <p className="text-red-400 text-sm mb-2">防衛側 (相手から) 勝率</p>
                  <p className="text-4xl font-black text-red-400">
                    {defenseWins + defenseLosses > 0 ? Math.round((defenseWins / (defenseWins + defenseLosses)) * 100) : 0}%
                  </p>
                  <p className="text-sm text-red-500/60 mt-2">{defenseWins}勝 {defenseLosses}敗</p>
                </div>
              </div>
            ) : (
              <p className="text-slate-500 text-center py-12">編成データがありません</p>
            )}

            {/* 編成の配置ポジション分析セクション */}
            {selectedTeam && (() => {
              const selectedTeamData = stats?.team_usage?.find((t:any) => t.canonical_id === selectedTeam);
              const positionStats = selectedTeamData?.position_stats || [];
              if (positionStats.length === 0) return null;
              return (
                <div className="space-y-3">
                  <button 
                    onClick={() => setIsPositionStatsOpen(!isPositionStatsOpen)}
                    className="w-full font-bold text-white flex items-center justify-between hover:bg-white/5 p-2 rounded-lg transition-colors"
                  >
                    <div className="flex items-center space-x-2">
                      <span className="text-lg">📊</span>
                      <span>編成の配置ポジション分析</span>
                    </div>
                    <ChevronDown className={`h-5 w-5 text-slate-400 transition-transform ${isPositionStatsOpen ? "" : "-rotate-90"}`} />
                  </button>
                  {isPositionStatsOpen && (
                  <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-hidden">
                    <table className="w-full text-center">
                      <thead>
                        <tr className="border-b border-white/10 bg-slate-900/50">
                          <th className="py-3 px-2 text-slate-400 font-bold text-sm">〇番目</th>
                          <th className="py-3 px-2 text-slate-400 font-bold text-sm">採用数</th>
                          <th className="py-3 px-2 text-slate-400 font-bold text-sm">勝率</th>
                          <th className="py-3 px-2 text-slate-400 font-bold text-sm">最終成績</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[1, 2, 3, 4, 5].map(pos => {
                          const ps = positionStats.find((p:any) => p.position === pos) || { count: 0, pct: 0, wins: 0, total: 0, win_rate: null, best_result: null };
                          return (
                            <tr key={pos} className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors">
                              <td className="py-3 px-2 text-white font-black text-lg">{pos}番目</td>
                              <td className="py-3 px-2">
                                <span className="text-white font-bold text-lg">{ps.count}</span>
                                <span className="text-slate-500 text-xs ml-0.5">人</span>
                                <br />
                                <span className="text-slate-400 text-xs">({ps.pct}%)</span>
                              </td>
                              <td className="py-3 px-2">
                                {ps.win_rate !== null ? (
                                  <>
                                    <span className={`font-black text-lg ${ps.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                      {ps.win_rate}%
                                    </span>
                                    <br />
                                    <span className="text-slate-500 text-[10px]">{ps.wins}W {ps.total - ps.wins}L</span>
                                  </>
                                ) : (
                                  <span className="text-slate-600 text-xs">対戦なし</span>
                                )}
                              </td>
                              <td className="py-3 px-2">
                                {ps.best_result ? (
                                  <span className={`inline-block px-3 py-1 text-xs font-bold rounded-full ring-1 ${
                                    ps.best_result === "優勝" ? "bg-amber-400/20 text-amber-300 ring-amber-400/50" :
                                    ps.best_result === "準優勝" ? "bg-slate-300/20 text-slate-200 ring-slate-300/50" :
                                    ps.best_result === "ベスト4" ? "bg-orange-500/20 text-orange-400 ring-orange-500/50" :
                                    ps.best_result === "ベスト8" ? "bg-blue-500/20 text-blue-400 ring-blue-500/50" :
                                    ps.best_result === "ベスト16" ? "bg-purple-500/20 text-purple-400 ring-purple-500/50" :
                                    ps.best_result === "ベスト32" ? "bg-slate-700/60 text-slate-400 ring-slate-600/50" :
                                    "bg-slate-800/60 text-slate-500 ring-slate-700/50"
                                  }`}>
                                    {ps.best_result}
                                  </span>
                                ) : (
                                  <span className="text-slate-600 text-xs">-</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  )}
                </div>
              );
            })()}

            {/* 採用した指揮官セクション */}
            {selectedTeam && (() => {
              const selectedTeamData = stats?.team_usage?.find((t:any) => t.canonical_id === selectedTeam);
              const adoptedPlayers = selectedTeamData?.adopted_players || [];
              if (adoptedPlayers.length === 0) return null;
              const resultColors: Record<string, string> = {
                "優勝":   "bg-amber-400/20 text-amber-300 ring-amber-400/50",
                "準優勝": "bg-slate-300/20 text-slate-200 ring-slate-300/50",
                "ベスト4":  "bg-orange-500/20 text-orange-400 ring-orange-500/50",
                "ベスト8":  "bg-blue-500/20 text-blue-400 ring-blue-500/50",
                "ベスト16": "bg-purple-500/20 text-purple-400 ring-purple-500/50",
                "ベスト32": "bg-slate-700/60 text-slate-400 ring-slate-600/50",
                "ベスト64": "bg-slate-800/60 text-slate-500 ring-slate-700/50",
              };
              return (
                <div className="mt-6 bg-slate-800/30 rounded-2xl ring-1 ring-white/5 p-5">
                  <button
                    onClick={() => setIsAdoptedPlayersOpen(!isAdoptedPlayersOpen)}
                    className="w-full font-bold text-white mb-2 flex items-center justify-between hover:bg-white/5 p-2 rounded-lg transition-colors"
                  >
                    <div className="flex items-center space-x-2">
                      <UserIcon size={18} className="text-purple-400" />
                      <span>この編成を採用した指揮官</span>
                    </div>
                    <ChevronDown className={`h-5 w-5 text-slate-400 transition-transform ${isAdoptedPlayersOpen ? "" : "-rotate-90"}`} />
                  </button>
                  {isAdoptedPlayersOpen && (
                  <div className="space-y-2">
                    {adoptedPlayers.map((ap: any, idx: number) => (
                      <div key={idx} className="flex items-center justify-between bg-slate-900/50 px-4 py-3 rounded-xl ring-1 ring-white/5">
                        <div className="flex items-center space-x-3">
                          <span className="text-xs font-bold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded ring-1 ring-indigo-500/20 whitespace-nowrap">
                            {ap.tournament_name}
                          </span>
                          <span className="font-bold text-slate-200 text-sm">{ap.player_name}</span>
                        </div>
                        <span className={`inline-block px-3 py-1 text-[10px] font-black rounded-full ring-1 ${resultColors[ap.result] ?? "bg-slate-800/60 text-slate-500 ring-slate-700/50"}`}>
                          {ap.result}
                        </span>
                      </div>
                    ))}
                  </div>
                  )}
                </div>
              );
            })()}

            {selectedTeam && matchupDetails.length > 0 && (() => {
              const stageOrder = [
                "決勝", "FINAL",
                "準決勝", "Best 4", "ベスト4",
                "Best 8", "ベスト8",
                "Best 16", "ベスト16",
                "Best 32", "ベスト32",
                "Best 64", "ベスト64",
                "不明"
              ];
              const availableStages = Array.from(new Set(matchupDetails.map(m => m.stage || "不明"))).sort((a: any, b: any) => {
                const indexA = stageOrder.indexOf(a);
                const indexB = stageOrder.indexOf(b);
                if (indexA !== -1 && indexB !== -1) return indexA - indexB;
                if (indexA !== -1) return -1;
                if (indexB !== -1) return 1;
                return a.localeCompare(b);
              });
              const filteredMatchupDetails = matchupDetails.filter((m: any) => {
                if (matchupFilterResult === "WIN" && !m.isWin) return false;
                if (matchupFilterResult === "LOSE" && m.isWin) return false;
                if (matchupFilterSide === "ATTACK" && !m.isAttacker) return false;
                if (matchupFilterSide === "DEFENSE" && m.isAttacker) return false;
                if (matchupFilterStage !== "ALL" && (m.stage || "不明") !== matchupFilterStage) return false;
                return true;
              });

              return (
              <div className="space-y-4 mt-8">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 space-y-3 sm:space-y-0">
                  <h3 className="font-bold text-white">この編成の対戦履歴</h3>
                  <div className="flex flex-wrap gap-2">
                    <select
                      className="bg-slate-900 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-purple-500"
                      value={matchupFilterResult}
                      onChange={e => setMatchupFilterResult(e.target.value as any)}
                    >
                      <option value="ALL">勝敗: すべて</option>
                      <option value="WIN">WIN</option>
                      <option value="LOSE">LOSE</option>
                    </select>
                    <select
                      className="bg-slate-900 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-purple-500"
                      value={matchupFilterSide}
                      onChange={e => setMatchupFilterSide(e.target.value as any)}
                    >
                      <option value="ALL">攻防: すべて</option>
                      <option value="ATTACK">攻撃</option>
                      <option value="DEFENSE">防衛</option>
                    </select>
                    <select
                      className="bg-slate-900 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-purple-500"
                      value={matchupFilterStage}
                      onChange={e => setMatchupFilterStage(e.target.value)}
                    >
                      <option value="ALL">ラウンド: すべて</option>
                      {availableStages.map(stage => (
                        <option key={stage} value={stage}>{stage}</option>
                      ))}
                    </select>
                  </div>
                </div>
                
                {filteredMatchupDetails.length > 0 ? (
                  <div className="space-y-2">
                    {filteredMatchupDetails.map((m: any, idx: number) => (
                      <div key={idx} 
                        onClick={() => handleTeamClick(m.opponentCanonical)}
                        className="bg-slate-800/30 hover:bg-slate-700/50 cursor-pointer transition-colors p-4 rounded-xl ring-1 ring-white/5 space-y-2"
                      >
                        {/* 大会名 & プレイヤー対戦情報 */}
                        <div className="flex items-center space-x-2 text-xs">
                          <span className="font-bold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded ring-1 ring-indigo-500/20 whitespace-nowrap">
                            {m.tournamentName || "不明"}
                          </span>
                          <span className="text-slate-400">
                            {m.attackerName} <span className="text-slate-600">vs</span> {m.defenderName}
                          </span>
                        </div>
                        {/* メイン行: ステージ・攻防・相手編成・勝敗 */}
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-4">
                            <div className="flex flex-col items-start space-y-1">
                              <div className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ring-1 ${
                                m.stage === "決勝" ? "bg-amber-500/20 text-amber-400 ring-amber-500/30" : 
                                m.stage?.includes("準決勝") ? "bg-orange-500/20 text-orange-400 ring-orange-500/30" :
                                "bg-slate-700/50 text-slate-400 ring-slate-600/50"
                              }`}>
                                {m.stage || "不明"}
                              </div>
                              <div className={`px-2 py-1 rounded text-xs font-bold w-fit ${m.isAttacker ? 'bg-blue-500/20 text-blue-400' : 'bg-red-500/20 text-red-400'}`}>
                                {m.isAttacker ? '攻撃' : '防衛'}
                              </div>
                            </div>
                            <div className="text-slate-400 text-sm mr-2">VS</div>
                            <TeamDisplay charIds={m.opponent} />
                          </div>
                          <div className={`font-black text-lg ${m.isWin ? 'text-emerald-400' : 'text-slate-600'}`}>
                            {m.isWin ? 'WIN' : 'LOSE'}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="bg-slate-800/30 rounded-xl ring-1 ring-white/5 p-8 text-center text-slate-400">
                    条件に一致する対戦履歴がありません
                  </div>
                )}
              </div>
              );
            })()}
          </div>
        )}



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
              <label className="block text-sm font-bold text-emerald-400 mb-3">キャラクターを選択して編成を逆引き</label>
              
              {/* フィルターUI */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterRarity} onChange={e => setFilterRarity(e.target.value)}>
                  <option value="">レアリティ (すべて)</option>
                  <option value="SSR">SSR</option>
                  <option value="SR">SR</option>
                  <option value="R">R</option>
                </select>
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterManufacturer} onChange={e => setFilterManufacturer(e.target.value)}>
                  <option value="">企業 (すべて)</option>
                  <option value="エリシオン">エリシオン</option>
                  <option value="ミシリス">ミシリス</option>
                  <option value="テトラ">テトラ</option>
                  <option value="ピルグリム">ピルグリム</option>
                  <option value="アブノーマル">アブノーマル</option>
                </select>
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterBurst} onChange={e => setFilterBurst(e.target.value)}>
                  <option value="">バースト (すべて)</option>
                  <option value="1">1 (A含む)</option>
                  <option value="2">2 (A含む)</option>
                  <option value="3">3 (A含む)</option>
                </select>
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterElement} onChange={e => setFilterElement(e.target.value)}>
                  <option value="">属性 (すべて)</option>
                  <option value="灼熱">灼熱</option>
                  <option value="水冷">水冷</option>
                  <option value="風圧">風圧</option>
                  <option value="鉄甲">鉄甲</option>
                  <option value="電撃">電撃</option>
                </select>
                <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterWeapon} onChange={e => setFilterWeapon(e.target.value)}>
                  <option value="">武器 (すべて)</option>
                  <option value="AR">アサルトライフル (AR)</option>
                  <option value="SG">ショットガン (SG)</option>
                  <option value="SMG">サブマシンガン (SMG)</option>
                  <option value="MG">マシンガン (MG)</option>
                  <option value="SR">スナイパーライフル (SR)</option>
                  <option value="RL">ロケットランチャー (RL)</option>
                </select>
              </div>

              <div className="flex flex-wrap gap-2">
                {filteredCharacters.map(c => {
                  const isSelected = searchChars.includes(c.id);
                  return (
                    <button
                      key={c.id}
                      onClick={() => {
                        if (isSelected) setSearchChars(searchChars.filter(id => id !== c.id));
                        else if (searchChars.length < 5) setSearchChars([...searchChars, c.id]);
                      }}
                      className={`relative w-12 h-12 rounded-lg overflow-hidden transition-all ${isSelected ? 'ring-2 ring-emerald-500 scale-110 shadow-lg' : 'ring-1 ring-white/10 opacity-70 hover:opacity-100'}`}
                      title={c.name}
                    >
                      {c.is_template_available ? (
                         <img src={`/api/char-icon/${c.id}.png`} loading="lazy" decoding="async" alt={c.name} className="w-full h-full object-cover" />
                      ) : (
                         <div className="w-full h-full bg-slate-800 flex items-center justify-center text-[10px] text-slate-400 font-bold text-center leading-tight">
                           {c.name.slice(0,4)}
                         </div>
                      )}
                      {isSelected && <div className="absolute inset-0 bg-emerald-500/20" />}
                    </button>
                  );
                })}
              </div>
              <div className="mt-4 flex items-center justify-between border-t border-emerald-500/20 pt-4">
                <span className="text-sm text-slate-400">選択中: {searchChars.length}/5</span>
                {searchChars.length > 0 && (
                  <button onClick={() => setSearchChars([])} className="text-sm text-emerald-400 hover:text-emerald-300 font-bold">
                    クリア
                  </button>
                )}
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="font-bold text-white mb-4">該当する編成一覧</h3>
              {searchChars.length === 0 ? (
                <p className="text-slate-500 text-center py-12">キャラクターを選択してください</p>
              ) : (
                <div className="space-y-3">
                  <PaginatedTeamList 
                    mode="cross"
                    tournamentIds={selectedTournamentIds} 
                    playServer={filterServer}
                    championshipId={selectedChampionshipId}
                    allCharacters={allCharacters}
                    characterIds={searchChars} 
                    onTeamClick={handleTeamClick} 
                    selectedTeam={selectedTeam} 
                    sortBy="count"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-slate-900 ring-1 ring-white/10 rounded-3xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
            {selectedCharacterDetailLoading ? (
              <div className="p-16 flex flex-col items-center justify-center space-y-4">
                <div className="animate-spin w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full" />
                <p className="text-slate-400 text-sm font-bold">キャラクター詳細を取得中...</p>
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
              const winRate = usageData?.win_rate || 0;
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
                <div className="p-8 space-y-8 animate-in fade-in zoom-in-95 duration-200">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-6">
                      <div className="w-24 h-24 rounded-2xl bg-slate-800 ring-2 ring-blue-500 overflow-hidden shadow-xl flex items-center justify-center">
                        {c.is_template_available ? (
                          <img src={`/api/char-icon/${c.id}.png`} loading="lazy" decoding="async" alt={c.name} className="w-full h-full object-cover" />
                        ) : (
                          <span className="text-2xl text-slate-500 font-black">{c.name.slice(0,3)}</span>
                        )}
                      </div>
                      <div>
                        <h2 className="text-3xl font-black text-white mb-2">{c.name}</h2>
                        <span className="px-3 py-1 bg-slate-800 text-slate-300 font-bold rounded-lg ring-1 ring-white/10 text-sm">
                          レアリティ: {c.rarity || "不明"}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Link
                        href={`/character/${selectedCharId}?tournaments=${selectedTournamentIds.join(',')}`}
                        className="flex items-center space-x-1.5 px-4 py-2 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-xl text-sm font-bold ring-1 ring-blue-500/30 transition-all whitespace-nowrap"
                        onClick={() => setSelectedCharId(null)}
                      >
                        <span>📄</span>
                        <span>フルページで詳細を見る</span>
                      </Link>
                      <button onClick={() => setSelectedCharId(null)} className="p-2 bg-white/5 hover:bg-white/10 rounded-full text-slate-400 hover:text-white transition-all">
                        <X size={24} />
                      </button>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-blue-500/10 p-6 rounded-2xl ring-1 ring-blue-500/20 flex flex-col items-center justify-center">
                      <p className="text-blue-400 text-sm font-bold mb-1">大会採用数</p>
                      <p className="text-3xl font-black text-blue-400">{usageCount} 回</p>
                    </div>
                    <div className="bg-emerald-500/10 p-6 rounded-2xl ring-1 ring-emerald-500/20 flex flex-col items-center justify-center">
                      <p className="text-emerald-400 text-sm font-bold mb-1">勝率 (非ミラー戦)</p>
                      <p className="text-3xl font-black text-emerald-400">{winRate}%</p>
                      <p className="text-xs text-emerald-500/60 mt-1">{charWins}勝 {charLosses}敗</p>
                    </div>
                  </div>

                  {/* 編成順（配置ポジション分析） */}
                  {hasPositionStats && (
                    <div className="space-y-3">
                      <h3 className="font-bold text-white flex items-center space-x-2">
                        <span className="text-lg">📊</span>
                        <span>部隊内の配置傾向</span>
                      </h3>
                      <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-hidden">
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
                                  <span className="text-slate-500 text-xs ml-0.5">回</span>
                                  <br />
                                  <span className="text-slate-400 text-xs">({ps.pct}%)</span>
                                </td>
                              ))}
                            </tr>
                            {/* ポジション別勝率 */}
                            <tr>
                              {usageData.position_stats.map((ps: any) => (
                                <td key={ps.position} className="py-3 px-2">
                                  {ps.win_rate !== null ? (
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
                          <span>上段: 配置回数（割合）</span>
                          <span>下段: そのポジションでの勝率</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 編成の配置傾向 */}
                  {hasTeamPositionStats && (
                    <div className="space-y-3">
                      <h3 className="font-bold text-white flex items-center space-x-2">
                        <span className="text-lg">📊</span>
                        <span>編成の配置傾向</span>
                      </h3>
                      <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-hidden">
                        <table className="w-full text-center">
                          <thead>
                            <tr className="border-b border-white/10 bg-slate-900/50">
                              <th className="py-2 px-2 text-slate-400 font-bold text-xs">〇番目</th>
                              <th className="py-2 px-2 text-slate-400 font-bold text-xs">採用数</th>
                              <th className="py-2 px-2 text-slate-400 font-bold text-xs">勝率</th>
                              <th className="py-2 px-2 text-slate-400 font-bold text-xs">最終成績</th>
                            </tr>
                          </thead>
                          <tbody>
                            {[1, 2, 3, 4, 5].map(pos => {
                              const ps = usageData.team_position_stats.find((p:any) => p.position === pos) || { count: 0, pct: 0, wins: 0, total: 0, win_rate: null, best_result: null };
                              return (
                                <tr key={pos} className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors">
                                  <td className="py-2 px-2 text-white font-bold text-sm">{pos}番目</td>
                                  <td className="py-2 px-2">
                                    <span className="text-white font-bold text-sm">{ps.count}</span>
                                    <span className="text-slate-500 text-[10px] ml-0.5">人</span>
                                    <br />
                                    <span className="text-slate-400 text-[10px]">({ps.pct}%)</span>
                                  </td>
                                  <td className="py-2 px-2">
                                    {ps.win_rate !== null ? (
                                      <>
                                        <span className={`font-bold text-sm ${ps.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                          {ps.win_rate}%
                                        </span>
                                        <br />
                                        <span className="text-slate-500 text-[10px]">{ps.wins}W {ps.total - ps.wins}L</span>
                                      </>
                                    ) : (
                                      <span className="text-slate-600 text-xs">対戦なし</span>
                                    )}
                                  </td>
                                  <td className="py-2 px-2">
                                    {ps.best_result ? (
                                      <span className={`inline-block px-2 py-0.5 text-[10px] font-bold rounded-full ring-1 ${
                                        ps.best_result === "優勝" ? "bg-amber-400/20 text-amber-300 ring-amber-400/50" :
                                        ps.best_result === "準優勝" ? "bg-slate-300/20 text-slate-200 ring-slate-300/50" :
                                        ps.best_result === "ベスト4" ? "bg-orange-500/20 text-orange-400 ring-orange-500/50" :
                                        ps.best_result === "ベスト8" ? "bg-blue-500/20 text-blue-400 ring-blue-500/50" :
                                        ps.best_result === "ベスト16" ? "bg-purple-500/20 text-purple-400 ring-purple-500/50" :
                                        ps.best_result === "ベスト32" ? "bg-slate-700/60 text-slate-400 ring-slate-600/50" :
                                        "bg-slate-800/60 text-slate-500 ring-slate-700/50"
                                      }`}>
                                        {ps.best_result}
                                      </span>
                                    ) : (
                                      <span className="text-slate-600 text-[10px]">-</span>
                                    )}
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
                      <span>よく一緒に編成されるキャラクター</span>
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
                                {ch.is_template_available ? (
                                  <img src={`/api/char-icon/${ch.id}.png`} loading="lazy" decoding="async" alt={ch.name} className="w-full h-full object-cover" />
                                ) : (
                                  <span className="text-[9px] text-slate-500 font-bold">{ch.name?.slice(0, 3)}</span>
                                )}
                              </div>
                              <span className="text-[9px] text-slate-300 w-12 truncate text-center" title={ch.name}>{ch.name}</span>
                              <span className="text-[9px] text-emerald-400 font-bold bg-emerald-400/10 px-1 rounded-full">
                                {ch.synergyCount}回 ({usageCount > 0 ? Math.round((ch.synergyCount / usageCount) * 100) : 0}%)
                              </span>
                            </div>
                          ))}
                          {burst1Chars.length === 0 && <span className="text-slate-500 text-xs p-2">該当なし</span>}
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
                                {ch.is_template_available ? (
                                  <img src={`/api/char-icon/${ch.id}.png`} loading="lazy" decoding="async" alt={ch.name} className="w-full h-full object-cover" />
                                ) : (
                                  <span className="text-[9px] text-slate-500 font-bold">{ch.name?.slice(0, 3)}</span>
                                )}
                              </div>
                              <span className="text-[9px] text-slate-300 w-12 truncate text-center" title={ch.name}>{ch.name}</span>
                              <span className="text-[9px] text-emerald-400 font-bold bg-emerald-400/10 px-1 rounded-full">
                                {ch.synergyCount}回 ({usageCount > 0 ? Math.round((ch.synergyCount / usageCount) * 100) : 0}%)
                              </span>
                            </div>
                          ))}
                          {burst2Chars.length === 0 && <span className="text-slate-500 text-xs p-2">該当なし</span>}
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
                                {ch.is_template_available ? (
                                  <img src={`/api/char-icon/${ch.id}.png`} loading="lazy" decoding="async" alt={ch.name} className="w-full h-full object-cover" />
                                ) : (
                                  <span className="text-[9px] text-slate-500 font-bold">{ch.name?.slice(0, 3)}</span>
                                )}
                              </div>
                              <span className="text-[9px] text-slate-300 w-12 truncate text-center" title={ch.name}>{ch.name}</span>
                              <span className="text-[9px] text-emerald-400 font-bold bg-emerald-400/10 px-1 rounded-full">
                                {ch.synergyCount}回 ({usageCount > 0 ? Math.round((ch.synergyCount / usageCount) * 100) : 0}%)
                              </span>
                            </div>
                          ))}
                          {burst3Chars.length === 0 && <span className="text-slate-500 text-xs p-2">該当なし</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <div className="space-y-4">
                    <h3 className="font-bold text-white flex items-center space-x-2">
                      <Users size={18} className="text-slate-400" />
                      <span>採用されている編成リスト</span>
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
                          <div key={idx} onClick={() => handleTeamClick(team.canonical_id)} className="flex flex-col bg-slate-800/50 hover:bg-slate-700/60 cursor-pointer transition-colors p-4 rounded-xl ring-1 ring-white/5 space-y-3">
                            {/* 編成アイコン行 */}
                            <div className="flex items-center justify-between">
                              <TeamDisplay charIds={team.character_ids} />
                              <div className="flex items-center space-x-2 shrink-0 ml-4">
                                {team.best_result && (
                                  <span className={`inline-block px-2 py-0.5 text-xs font-bold rounded-full ring-1 ${teamResultClass}`}>
                                    {team.best_result}
                                  </span>
                                )}
                                <span className="text-slate-400 font-bold bg-slate-900 px-2 py-0.5 rounded-lg ring-1 ring-white/10 text-xs">
                                  {team.count} 採用
                                </span>
                              </div>
                            </div>
                            {/* 勝率・勝敗行 */}
                            {team.total_matches > 0 && (
                              <div className="flex items-center space-x-4 pt-2 border-t border-white/5">
                                <div className="flex items-center space-x-2">
                                  <span className="text-[10px] text-slate-500 font-bold uppercase">勝率</span>
                                  <span className={`text-lg font-black ${team.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                    {team.win_rate}%
                                  </span>
                                </div>
                                <div className="h-4 w-px bg-white/10"></div>
                                <div className="flex items-center space-x-2 text-xs font-bold">
                                  <span className="text-emerald-400">{team.win_count}勝</span>
                                  <span className="text-slate-500">{team.total_matches - team.win_count}敗</span>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {relatedTeams.length === 0 && (
                        <p className="text-slate-500 text-sm text-center py-4">データがありません</p>
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
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#0a0f1e] flex items-center justify-center">
          <div className="text-center space-y-4">
            <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-slate-400 font-bold">データを読み込んでいます...</p>
          </div>
        </main>
      }
    >
      <DashboardContent />
    </Suspense>
  );
}
