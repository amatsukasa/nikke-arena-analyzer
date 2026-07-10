"use client";
export const dynamic = 'force-dynamic';
import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ChevronDown, ChevronLeft, TrendingUp, Users, Swords, Search, X, Trophy, ShieldAlert, User as UserIcon, Globe } from "lucide-react";
import Link from "next/link";
import PaginatedTeamList from "../../../../components/PaginatedTeamList";
import SharedTeamDisplay from "../../../../components/TeamDisplay";
import CharacterUsageByResultRanking from "../../../../components/CharacterUsageByResultRanking";
import TeamMatchupHistory from "../../../../components/TeamMatchupHistory";
import { getCharIconUrl } from "@/utils/charIcon";

type DashboardTab = "review" | "my_dashboard" | "overview" | "winrate" | "team_winrate" | "matchups" | "search" | "best8";
const TOURNAMENT_TABS = new Set<DashboardTab>([
  "review",
  "team_winrate",
  "matchups",
  "search",
  "overview",
  "winrate",
  "my_dashboard",
  "best8",
]);

export default function Dashboard() {
  const params = useParams();
  const searchParams = useSearchParams();
  const id = params.id;

  // URLクエリパラメータから初期タブ・編成を復元（キャラ詳細ページからの遷移用）
  const requestedTab = searchParams.get("tab") as DashboardTab | null;
  const initialTab = requestedTab && TOURNAMENT_TABS.has(requestedTab)
    ? requestedTab
    : "review";
  const initialTeam = searchParams.get("team");

  const [tournament, setTournament] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [matchups, setMatchups] = useState<any[]>([]);
  const [allCharacters, setAllCharacters] = useState<any[]>([]);
  const [bracketData, setBracketData] = useState<any>(null);
  const [myPlayerDetails, setMyPlayerDetails] = useState<any>(null);
  const [best8Data, setBest8Data] = useState<any[]>([]);
  const [dashboardSummary, setDashboardSummary] = useState<any>(null);
  const [isPrivateTournament, setIsPrivateTournament] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [loading, setLoading] = useState(true);

  const [authError, setAuthError] = useState(false);
  
  const [activeTab, setActiveTab] = useState<DashboardTab>(initialTab);

  // For matchups
  const [selectedTeam, setSelectedTeam] = useState<string>(initialTeam || "");
  const [isPositionStatsOpen, setIsPositionStatsOpen] = useState(true);
  const [isAdoptedPlayersOpen, setIsAdoptedPlayersOpen] = useState(true);

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
  const [visibleTeamCount, setVisibleTeamCount] = useState(10);

  useEffect(() => {
    setVisibleTeamCount(10);
  }, [stats, teamMinMatches, teamBestResult, teamMinWinRate, searchChars]);

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

  // 1. 初回読み込み時に localStorage からシードを復元
  useEffect(() => {
    const savedSeed = localStorage.getItem(`nikke_dashboard_seed_${id}`);
    if (savedSeed) {
      setSelectedSeed(parseInt(savedSeed));
    }
    setIsFirstLoad(false);
  }, [id]);

  // 2. シードが変更されたら localStorage に保存
  useEffect(() => {
    if (!isFirstLoad) {
      localStorage.setItem(`nikke_dashboard_seed_${id}`, selectedSeed.toString());
    }
  }, [selectedSeed, id, isFirstLoad]);

  useEffect(() => {
    if (activeTab === "my_dashboard") {
      setMyPlayerDetails(null);
    }
  }, [selectedSeed, activeTab]);

  const [tournamentId, setTournamentId] = useState<number | null>(null);

  useEffect(() => {
    if (isFirstLoad) return;
    if (id) {
      setTournamentId(parseInt(id as string));
    }
  }, [id, isFirstLoad]);

  useEffect(() => {
    if (isFirstLoad || !tournamentId) return;

    const fetchData = async () => {
      setLoading(true);
      try {
        const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
        const authHeaders: any = token ? { "Authorization": `Bearer ${token}` } : {};
        const timestamp = Date.now();
        
        const tournUrl = `/api/tournaments/${tournamentId}?t=${timestamp}`;
        const tournRes = await fetch(tournUrl, { cache: 'no-store', headers: authHeaders });
        if (!tournRes.ok) {
          if (tournRes.status === 401) setAuthError(true);
          else {
            const text = await tournRes.text();
            console.error("API error", tournRes.status, tournUrl, text.slice(0, 300));
          }
          setLoading(false);
          return;
        }
        const tournData = await tournRes.json();
        setTournament(tournData);
        const isPrivate = tournData.publication_status !== "published";
        setIsPrivateTournament(isPrivate);

        if (isPrivate) {
          console.info(`[private-dashboard] skipped eager fetch tournament=${tournamentId}`);
          const urls = [
            `/api/characters?t=${timestamp}`,
            `/api/tournaments/${tournamentId}/dashboard/summary?t=${timestamp}`
          ];
          const responses = await Promise.all(urls.map(url => fetch(url, { cache: 'no-store', headers: authHeaders })));

          for (let i = 0; i < responses.length; i++) {
            const res = responses[i];
            if (!res.ok) {
              if (res.status === 401) {
                setAuthError(true);
                setLoading(false);
                return;
              }
              const text = await res.text();
              console.error("API error", res.status, urls[i], text.slice(0, 300));
            }
          }

          if (responses.some(res => !res.ok)) {
            setLoading(false);
            return;
          }

          const [charsData, summaryData] = await Promise.all(responses.map(res => res.json()));
          setAllCharacters(charsData);
          setDashboardSummary(summaryData);
          if (!requestedTab) {
            setActiveTab("review");
          }
          return;
        }

        const urls = [
          `/api/characters?t=${timestamp}`,
          `/api/tournaments/${tournamentId}/dashboard/summary?t=${timestamp}`,
          `/api/tournaments/${tournamentId}/bracket?t=${timestamp}`,
          `/api/tournaments/${tournamentId}/dashboard/player-stats?seed=${selectedSeed}&t=${timestamp}`,
          `/api/tournaments/${tournamentId}/dashboard/best8-decks?t=${timestamp}`,
          `/api/tournaments/${tournamentId}/dashboard/stats?t=${timestamp}`
        ];
        const responses = await Promise.all(urls.map(url => fetch(url, { cache: 'no-store', headers: authHeaders })));

        for (let i = 0; i < responses.length; i++) {
          const res = responses[i];
          if (!res.ok) {
            if (res.status === 401) {
              setAuthError(true);
              setLoading(false);
              return;
            }
            const text = await res.text();
            console.error("API error", res.status, urls[i], text.slice(0, 300));
          }
        }

        if (responses.some(res => !res.ok)) {
          setLoading(false);
          return;
        }

        const [charsData, summaryData, bracketDataRaw, detailsData, best8DataRaw, statsData] = await Promise.all(
          responses.map(res => res.json())
        );

        setAllCharacters(charsData);
        setDashboardSummary(summaryData);
        setBracketData(bracketDataRaw);
        setMyPlayerDetails(detailsData);
        setBest8Data(best8DataRaw);
        setStats(statsData);
        if (!requestedTab) {
          setActiveTab(summaryData?.readiness?.can_publish === false ? "review" : "team_winrate");
        }
        
        if (statsData.team_usage && statsData.team_usage.length > 0) {
          setSelectedTeam(statsData.team_usage[0].canonical_id);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id, isFirstLoad, tournamentId, requestedTab]);

  useEffect(() => {
    const hasFullStats = Boolean(stats?.character_usage_by_result && stats?.team_usage);
    if (!isPrivateTournament || !tournamentId || hasFullStats) return;
    if (activeTab !== "overview" && activeTab !== "matchups") return;

    const fetchStats = async () => {
      setAnalysisLoading(true);
      try {
        const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
        const authHeaders: any = token ? { "Authorization": `Bearer ${token}` } : {};
        const url = `/api/tournaments/${tournamentId}/dashboard/stats?t=${Date.now()}`;
        const res = await fetch(url, { cache: "no-store", headers: authHeaders });
        if (!res.ok) {
          if (res.status === 401) setAuthError(true);
          else console.error("API error", res.status, url, (await res.text()).slice(0, 300));
          return;
        }
        const data = await res.json();
        setStats(data);
        if (data.team_usage && data.team_usage.length > 0 && !selectedTeam) {
          setSelectedTeam(data.team_usage[0].canonical_id);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setAnalysisLoading(false);
      }
    };

    fetchStats();
  }, [activeTab, isPrivateTournament, tournamentId, stats, selectedTeam]);

  useEffect(() => {
    if (!isPrivateTournament || !tournamentId || stats) return;
    if (activeTab !== "winrate") return;

    const fetchCharacterWinrates = async () => {
      setAnalysisLoading(true);
      try {
        const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
        const authHeaders: any = token ? { "Authorization": `Bearer ${token}` } : {};
        const url = `/api/tournaments/${tournamentId}/dashboard/character-winrates?t=${Date.now()}`;
        const res = await fetch(url, { cache: "no-store", headers: authHeaders });
        if (!res.ok) {
          if (res.status === 401) setAuthError(true);
          else console.error("API error", res.status, url, (await res.text()).slice(0, 300));
          return;
        }
        const data = await res.json();
        const characterUsage = data.character_winrates || data.character_stats || [];
        setStats({
          character_usage: characterUsage,
          character_stats: characterUsage,
          team_usage: [],
        });
      } catch (e) {
        console.error(e);
      } finally {
        setAnalysisLoading(false);
      }
    };

    fetchCharacterWinrates();
  }, [activeTab, isPrivateTournament, tournamentId, stats]);

  useEffect(() => {
    if (!tournamentId || activeTab !== "my_dashboard") return;
    if (bracketData && myPlayerDetails) return;

    const fetchMyDashboard = async () => {
      setAnalysisLoading(true);
      try {
        const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
        const authHeaders: any = token ? { "Authorization": `Bearer ${token}` } : {};
        const timestamp = Date.now();
        const urls = [
          `/api/tournaments/${tournamentId}/bracket?t=${timestamp}`,
          `/api/tournaments/${tournamentId}/dashboard/player-stats?seed=${selectedSeed}&t=${timestamp}`,
        ];
        const responses = await Promise.all(urls.map(url => fetch(url, { cache: "no-store", headers: authHeaders })));
        for (let i = 0; i < responses.length; i++) {
          if (!responses[i].ok) {
            if (responses[i].status === 401) setAuthError(true);
            else console.error("API error", responses[i].status, urls[i], (await responses[i].text()).slice(0, 300));
            return;
          }
        }
        const [bracketDataRaw, detailsData] = await Promise.all(responses.map(res => res.json()));
        setBracketData(bracketDataRaw);
        setMyPlayerDetails(detailsData);
      } catch (e) {
        console.error(e);
      } finally {
        setAnalysisLoading(false);
      }
    };

    fetchMyDashboard();
  }, [activeTab, tournamentId, selectedSeed, bracketData, myPlayerDetails]);

  useEffect(() => {
    if (activeTab !== "best8" || !tournamentId) return;
    if (best8Data && best8Data.length > 0) return;

    const fetchBest8 = async () => {
      try {
        const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
        const authHeaders: any = token ? { "Authorization": `Bearer ${token}` } : {};
        const url = `/api/tournaments/${tournamentId}/dashboard/best8-decks?t=${Date.now()}`;
        const res = await fetch(url, { cache: 'no-store', headers: authHeaders });
        if (!res.ok) {
          if (res.status === 401) {
            setAuthError(true);
            return;
          }
          const text = await res.text();
          console.error("API error", res.status, url, text.slice(0, 300));
          return;
        }
        const data = await res.json();
        setBest8Data(data);
      } catch (e) {
        console.error(e);
      }
    };
    fetchBest8();
  }, [activeTab, tournamentId, best8Data]);

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
    if (activeTab !== "matchups") return;
    if (matchups.length > 0 || !tournamentId) return;

    const fetchMatchups = async () => {
      try {
        const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
        const authHeaders: any = token ? { "Authorization": `Bearer ${token}` } : {};
        const timestamp = Date.now();
        const url = `/api/tournaments/${tournamentId}/dashboard/matchups?t=${timestamp}`;
        const res = await fetch(url, { cache: 'no-store', headers: authHeaders });
        if (!res.ok) {
          if (res.status === 401) {
            setAuthError(true);
            return;
          }
          const text = await res.text();
          console.error("API error", res.status, url, text.slice(0, 300));
          return;
        }
        const matchupsData = await res.json();
        setMatchups(matchupsData.matchups || matchupsData);
      } catch (e) {
        console.error(e);
      }
    };
    fetchMatchups();
  }, [activeTab, tournamentId, matchups.length]);

  if (authError) return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4">
      <div className="bg-slate-900/80 backdrop-blur-xl border border-white/10 rounded-3xl p-8 max-w-md w-full text-center space-y-6 shadow-2xl">
        <div className="w-16 h-16 bg-blue-500/10 rounded-full flex items-center justify-center mx-auto text-blue-400 text-3xl">
          🔒
        </div>
        <div className="space-y-2">
          <h2 className="text-2xl font-black text-white">ログインが必要です</h2>
          <p className="text-slate-400 text-sm">
            メンバー専用ダッシュボードを閲覧するには、アカウントへのログイン（または権限の認証）が必要です。
          </p>
        </div>
        <div className="flex flex-col gap-3">
          <Link
            href="/secret-login"
            className="w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold rounded-xl shadow-lg shadow-blue-500/20 transition-all text-center"
          >
            ログインページへ
          </Link>
          <Link
            href={`/tournament/${id}`}
            className="w-full py-3 px-4 bg-white/5 hover:bg-white/10 text-slate-300 font-bold rounded-xl transition-all text-center text-sm"
          >
            トーナメント表に戻る
          </Link>
        </div>
      </div>
    </div>
  );

  if (loading) return (
    <div className="flex h-screen items-center justify-center">
      <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );

  const collectionLabel = (value: string | null | undefined) => {
    const labels: Record<string, string> = {
      none: "なし",
      r_0_14: "R 0-14",
      r_15: "R 15",
      sr_0_14: "SR 0-14",
      sr_15: "SR 15",
      treasure_0_14: "宝物 0-14",
      treasure_15: "宝物 15",
      unknown: "判定不能",
    };
    return value ? labels[value] || "判定不能" : "未登録";
  };

  const collectionBadgeUrl = (value: string | null | undefined) => {
    const badgeFiles: Record<string, string> = {
      none: "none.png",
      r_0_14: "r-0-14.png",
      r_15: "r-15.png",
      sr_0_14: "sr-0-14.png",
      sr_15: "sr-15.png",
      treasure_0_14: "treasure-0-14.png",
      treasure_15: "treasure-15.png",
      unknown: "unknown.png",
    };
    return `/collection-badges/${value ? badgeFiles[value] || "unknown.png" : "unregistered.png"}`;
  };

  // Helper to render a team
  const TeamDisplay = ({
    charIds,
    allCharacters: charsParam,
    collectionLevels,
  }: {
    charIds: number[],
    allCharacters?: any[],
    collectionLevels?: Array<string | null>,
  }) => {
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
                <span className="text-[9px] text-slate-500 w-10 truncate text-center" title="空枠">空枠</span>
              </div>
            );
          }
          return (
            <div key={i} className="flex flex-col items-center space-y-1 cursor-pointer group" onClick={(e) => { e.stopPropagation(); setSelectedCharId(c.id); }}>
              <div className="relative w-10 h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 group-hover:ring-blue-500 overflow-hidden flex items-center justify-center transition-all">
                {getCharIconUrl(c) ? (
                  <img src={getCharIconUrl(c)} loading="lazy" decoding="async" alt={c?.name || "不明"} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-[10px] text-slate-500 font-bold leading-tight text-center">{c?.name?.slice(0, 3) || "不明"}</span>
                )}
                {collectionLevels && (
                  <img
                    src={collectionBadgeUrl(collectionLevels[i])}
                    alt={`コレクション: ${collectionLabel(collectionLevels[i])}`}
                    title={`コレクション: ${collectionLabel(collectionLevels[i])}`}
                    className="absolute left-0 top-1/2 z-10 h-4 w-4 -translate-y-1/2 drop-shadow-md"
                  />
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
      attackerTeam: m.attacker_team,
      defenderTeam: m.defender_team,
      attackerCollections: m.attacker_collections,
      defenderCollections: m.defender_collections,
      canonicalAttacker: m.canonical_attacker,
      canonicalDefender: m.canonical_defender,
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

  // 横断モード非対応タブでは選択UIを表示しない
  const showTournamentSelector = activeTab !== "my_dashboard" && activeTab !== "best8";
  const hasFullStats = Boolean(stats?.character_usage_by_result && stats?.team_usage);

  return (
    <main className="p-6 md:p-12 max-w-6xl mx-auto space-y-8 pb-24">
      {/* Header */}
      <div className="flex items-center space-x-4 mb-8">
        <Link href={`/tournament/${id}`}>
          <div className="p-2 bg-slate-800 hover:bg-slate-700 rounded-full transition-colors cursor-pointer ring-1 ring-white/10 shadow-lg">
            <ChevronLeft size={24} className="text-slate-300" />
          </div>
        </Link>
        <div className="flex-1">
          <h1 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">
            大会分析
          </h1>
          <p className="text-slate-400 text-sm mt-1">{tournament?.name} の分析</p>
        </div>
        
        <div className="bg-slate-900/80 backdrop-blur-xl p-4 rounded-2xl ring-2 ring-blue-500 shadow-[0_0_20px_rgba(59,130,246,0.3)] flex items-center space-x-4">
           <div className="text-right hidden md:block">
              <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">分析対象プレイヤー</p>
              <p className="text-sm font-bold text-slate-200">シード {selectedSeed}</p>
           </div>
           <select 
             value={selectedSeed}
             onChange={(e) => setSelectedSeed(parseInt(e.target.value))}
             className="bg-slate-800 border border-white/20 rounded-lg px-3 py-2 text-sm font-bold text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-400 cursor-pointer hover:bg-slate-700 transition-all"
           >
             {seeds.map(s => (
                <option key={s} value={s}>シード {s} を表示</option>
             ))}
           </select>
        </div>
      </div>

      {/* 単体大会分析専用モード */}

      {/* Tabs */}
      <div className="flex bg-slate-900/80 backdrop-blur-xl p-1.5 rounded-2xl ring-1 ring-white/10 shadow-2xl overflow-x-auto">
        <button
          onClick={() => setActiveTab("review")}
          className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "review" ? "bg-slate-600 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
        >
          <ShieldAlert size={18} />
          <span>入力確認</span>
        </button>
        <button
          onClick={() => setActiveTab("team_winrate")}
          className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "team_winrate" ? "bg-pink-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
        >
          <Users size={18} />
          <span>編成別勝率</span>
        </button>
        <button 
          onClick={() => setActiveTab("matchups")}
          className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "matchups" ? "bg-purple-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
        >
          <Swords size={18} />
          <span>編成詳細</span>
        </button>
        <button 
          onClick={() => setActiveTab("search")}
          className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "search" ? "bg-emerald-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
        >
          <Search size={18} />
          <span>シナジー逆引き検索</span>
        </button>
        <button
          onClick={() => setActiveTab("overview")}
          className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "overview" ? "bg-blue-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
        >
          <TrendingUp size={18} />
          <span>トレンド分析</span>
        </button>
        <button
          onClick={() => setActiveTab("winrate")}
          className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "winrate" ? "bg-red-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
        >
          <Trophy size={18} />
          <span>キャラ別勝率</span>
        </button>
        <button
          onClick={() => setActiveTab("my_dashboard")}
          className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "my_dashboard" ? "bg-amber-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
        >
          <UserIcon size={18} />
          <span>個人成績</span>
        </button>
        <button
          onClick={() => setActiveTab("best8")}
          className={`flex items-center space-x-2 px-6 py-3 rounded-xl font-bold transition-all whitespace-nowrap ${activeTab === "best8" ? "bg-indigo-500 text-white shadow-lg" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"}`}
        >
          <Trophy size={18} />
          <span>Best8編成（大会別）</span>
        </button>
      </div>

      {/* Content */}
      <div className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-6 md:p-8 rounded-3xl shadow-2xl min-h-[500px]">
        {activeTab === "review" && (
          <div className="space-y-8 animate-in fade-in zoom-in-95 duration-300">
            <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="text-2xl font-black text-slate-100">入力確認</h2>
                <p className="mt-1 text-sm text-slate-400">{tournament?.name}</p>
              </div>
              <span className={`w-fit rounded-full px-3 py-1 text-xs font-bold ring-1 ${
                tournament?.publication_status === "published"
                  ? "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30"
                  : "bg-amber-500/10 text-amber-300 ring-amber-500/30"
              }`}>
                {tournament?.publication_status === "published" ? "公開中" : "非公開"}
              </span>
            </div>

            {dashboardSummary ? (
              <>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <div className="rounded-2xl bg-slate-800/50 p-5 ring-1 ring-white/10">
                    <p className="text-xs font-bold text-slate-500">登録済みプレイヤー</p>
                    <p className="mt-2 text-3xl font-black text-white">
                      {dashboardSummary.registered_player_count}
                      <span className="text-lg text-slate-500">/{dashboardSummary.expected_player_count ?? 64}</span>
                    </p>
                  </div>
                  <div className="rounded-2xl bg-slate-800/50 p-5 ring-1 ring-white/10">
                    <p className="text-xs font-bold text-slate-500">登録済み試合</p>
                    <p className="mt-2 text-3xl font-black text-white">
                      {dashboardSummary.registered_match_count}
                      <span className="text-lg text-slate-500">/{dashboardSummary.expected_match_count ?? 63}</span>
                    </p>
                  </div>
                  <div className="rounded-2xl bg-slate-800/50 p-5 ring-1 ring-white/10">
                    <p className="text-xs font-bold text-slate-500">登録済みの編成</p>
                    <p className="mt-2 text-3xl font-black text-white">
                      {dashboardSummary.registered_team_count ?? dashboardSummary.registered_representative_team_count}
                      <span className="text-lg text-slate-500">/{dashboardSummary.expected_team_count ?? 320}</span>
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                  <section className="rounded-2xl bg-slate-800/40 p-5 ring-1 ring-white/10">
                    <h3 className="mb-3 text-sm font-black text-slate-200">未登録シード</h3>
                    <div className="flex max-h-44 flex-wrap gap-2 overflow-y-auto">
                      {(dashboardSummary.missing_seed_numbers || []).slice(0, 64).map((seed: number) => (
                        <span key={seed} className="rounded-md bg-slate-900 px-2 py-1 text-xs font-bold text-slate-400 ring-1 ring-white/5">
                          {seed}
                        </span>
                      ))}
                      {(dashboardSummary.missing_seed_numbers || []).length === 0 && (
                        <p className="text-sm text-slate-500">なし</p>
                      )}
                    </div>
                  </section>

                  <section className="rounded-2xl bg-slate-800/40 p-5 ring-1 ring-white/10">
                    <h3 className="text-sm font-black text-slate-200">編成データ未作成のプレイヤー</h3>
                    <p className="mb-3 mt-1 text-xs text-slate-500">PlayerレコードはあるがDeckSetなし</p>
                    <div className="max-h-44 space-y-2 overflow-y-auto">
                      {(dashboardSummary.players_without_decks || []).map((player: any) => (
                        <div key={player.id} className="flex items-center justify-between rounded-lg bg-slate-900 px-3 py-2 text-xs ring-1 ring-white/5">
                          <span className="font-bold text-slate-200">Seed {player.seed_number}</span>
                          <span className="text-slate-500">{player.name}</span>
                        </div>
                      ))}
                      {(dashboardSummary.players_without_decks || []).length === 0 && (
                        <p className="text-sm text-slate-500">なし</p>
                      )}
                    </div>
                  </section>

                  <section className="rounded-2xl bg-slate-800/40 p-5 ring-1 ring-white/10">
                    <h3 className="mb-3 text-sm font-black text-slate-200">欠損っぽい編成</h3>
                    <div className="max-h-44 space-y-2 overflow-y-auto">
                      {(dashboardSummary.players_with_incomplete_decks || []).map((player: any) => (
                        <div key={player.id} className="rounded-lg bg-slate-900 px-3 py-2 text-xs ring-1 ring-white/5">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-slate-200">Seed {player.seed_number}</span>
                            <span className="text-slate-500">{player.name}</span>
                          </div>
                          <p className="mt-1 text-slate-500">Team {player.incomplete_team_numbers.join(", ")}</p>
                        </div>
                      ))}
                      {(dashboardSummary.players_with_incomplete_decks || []).length === 0 && (
                        <p className="text-sm text-slate-500">なし</p>
                      )}
                    </div>
                  </section>
                </div>
              </>
            ) : (
              <div className="flex h-64 items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-500 border-t-transparent" />
              </div>
            )}
          </div>
        )}
        {(((activeTab === "overview" || activeTab === "matchups") && !hasFullStats) || (activeTab === "winrate" && !stats)) && (
          <div className="flex h-64 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
          </div>
        )}
        
        {/* MY DASHBOARD TAB */}
        {activeTab === "my_dashboard" && (
           <div className="space-y-8 animate-in fade-in zoom-in-95 duration-300">
             <div className="text-center mb-8">
                <h2 className="text-2xl font-black text-slate-100">プレイヤー成績</h2>
                <p className="text-slate-400 mt-1">シード番号: {selectedSeed}</p>
             </div>

             {myPlayer && myDecks.length > 0 ? (
                <div className="max-w-4xl mx-auto space-y-8">
                   {/* Profile Header */}
                   <div className="flex flex-col md:flex-row items-center bg-slate-800/50 p-8 rounded-3xl ring-1 ring-white/10 shadow-2xl space-y-6 md:space-y-0 md:space-x-8 relative overflow-hidden">
                      <div className="absolute top-0 right-0 p-8 opacity-10 pointer-events-none">
                         <Trophy size={160} />
                      </div>
                      
                      <div className="w-32 h-32 rounded-full border-4 border-amber-500 shadow-[0_0_30px_rgba(245,158,11,0.3)] bg-slate-900 overflow-hidden shrink-0 z-10 flex items-center justify-center">
                          {myPlayerDetails?.player?.icon_url ? (
                             <img src={myPlayerDetails.player.icon_url.includes('?') ? myPlayerDetails.player.icon_url : `${myPlayerDetails.player.icon_url}?t=${Date.now()}`} alt="Player Icon" className="w-full h-full object-cover" />
                          ) : (
                             <div className="text-slate-600">
                                <UserIcon size={64} />
                             </div>
                          )}
                       </div>

                      <div className="flex-1 text-center md:text-left z-10">
                         <p className="text-amber-400 font-bold mb-1 text-sm tracking-widest uppercase">Player Profile</p>
                         <h3 className="text-4xl font-black text-white mb-2">{myPlayer.name}</h3>
                         <div className="inline-block bg-amber-500/10 border border-amber-500/30 text-amber-400 px-4 py-2 rounded-full font-black text-lg shadow-inner mt-2">
                            {myTournamentResult}
                         </div>
                      </div>
                   </div>

                   {/* Decks */}
                   <div className="bg-slate-800/30 p-6 md:p-8 rounded-3xl ring-1 ring-white/5">
                      <h4 className="text-xl font-bold text-slate-200 mb-6 flex items-center space-x-2">
                         <ShieldAlert className="text-blue-400" />
                         <span>登録編成と戦績</span>
                      </h4>
                      <div className="space-y-4">
                         {myDecks.map((deck: any) => (
                            <div 
                              key={deck.team_number} 
                              onClick={() => handleTeamClick(deck.canonical_id)}
                              className="flex flex-col md:flex-row items-center justify-between bg-slate-800/50 hover:bg-slate-700/60 transition-colors p-4 md:p-6 rounded-2xl ring-1 ring-white/5 cursor-pointer"
                            >
                               <div className="flex items-center space-x-6 mb-4 md:mb-0">
                                  <div className="flex flex-col items-center justify-center w-12 h-12 rounded-xl bg-slate-900 ring-1 ring-white/10 shrink-0">
                                     <span className="text-[10px] text-slate-500 font-bold tracking-wider">TEAM</span>
                                     <span className="text-xl font-black text-slate-200">{deck.team_number}</span>
                                  </div>
                                  <SharedTeamDisplay
                                    charIds={deck.character_ids}
                                    allCharacters={allCharacters}
                                    collectionLevels={deck.collection_levels}
                                    onCharacterClick={setSelectedCharId}
                                  />
                               </div>
                               
                               <div className="flex flex-col items-end">
                                  <div className="flex items-center space-x-3 bg-slate-900 px-4 py-2 rounded-xl ring-1 ring-white/5">
                                     <div className="flex flex-col text-right">
                                        <span className="text-[10px] text-slate-500 font-bold uppercase">Win Rate</span>
                                        <span className={`text-xl font-black ${deck.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                           {deck.win_rate}%
                                        </span>
                                     </div>
                                     <div className="h-8 w-px bg-white/10 mx-2"></div>
                                     <div className="flex flex-col text-left">
                                        <span className="text-xs font-bold text-emerald-400">{deck.wins} WIN</span>
                                        <span className="text-xs font-bold text-slate-500">{deck.losses} LOSE</span>
                                     </div>
                                  </div>
                               </div>
                            </div>
                         ))}
                      </div>
                   </div>
                </div>
             ) : (
                <div className="flex flex-col items-center justify-center h-64 bg-slate-800/30 rounded-3xl ring-1 ring-white/5 border border-dashed border-slate-600">
                   <UserIcon size={48} className="text-slate-600 mb-4" />
                   <p className="text-xl font-bold text-slate-400">まだ情報が登録されていません。</p>
                   <p className="text-slate-500 mt-2">トーナメント表からあなたの編成（シード {mySeed}）を登録してください。</p>
                </div>
             )}
           </div>
        )}

        {/* OVERVIEW TAB */}
        {activeTab === "overview" && hasFullStats && (
           <div className="space-y-12 animate-in fade-in zoom-in-95 duration-300">
            <CharacterUsageByResultRanking
              stats={stats}
              allCharacters={allCharacters}
              onSelectCharacter={setSelectedCharId}
            />
            {false && (
            <section>
              <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
                <Users className="text-blue-400" />
                <span>キャラクター採用率ランキング</span>
              </h2>
              <div className="overflow-x-auto rounded-xl ring-1 ring-white/10 shadow-2xl bg-slate-900/50">
                {(() => {
                  // 採用数でグループ化
                  const grouped: { count: number; entries: any[] }[] = [];
                  const sorted = [...stats.character_usage].sort((a: any, b: any) => b.count - a.count);
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
                                          {getCharIconUrl(c) ? (
                                            <img src={getCharIconUrl(c)} loading="lazy" decoding="async" alt={c.name} className="w-full h-full object-cover" />
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
                        {stats.character_usage.length === 0 && (
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
            )}
            <section>
              <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
                <Users className="text-emerald-400" />
                <span>編成（5名組み合わせ）使用率ランキング</span>
              </h2>
              {/* レスポンシブ統合リスト: PCでは行、スマホではカード（画像DOMは1つのみ） */}
              <div className="space-y-3">
                {/* PC用ヘッダー行 */}
                <div className="hidden md:grid grid-cols-12 gap-4 px-6 py-3 text-xs font-bold text-slate-400 bg-slate-900/80 rounded-xl border border-white/5">
                  <div className="col-span-1">順位</div>
                  <div className="col-span-5">編成</div>
                  <div className="col-span-2 text-center">最終成績</div>
                  <div className="col-span-2 text-right">勝率</div>
                  <div className="col-span-2 text-right">採用数</div>
                </div>

                {(stats?.team_usage ?? []).slice(0, visibleTeamCount).map((team: any, idx: number) => {
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
                  const totalPlayers = 64;
                  const adoptionPct = Math.round((team.count / totalPlayers) * 100);
                  return (
                    <div
                      key={idx}
                      onClick={() => handleTeamClick(team.canonical_id)}
                      className="bg-slate-800/50 hover:bg-slate-700/60 cursor-pointer transition-colors p-4 rounded-xl ring-1 ring-white/10 flex flex-col md:grid md:grid-cols-12 md:items-center gap-3"
                    >
                      {/* 上部・左部: スマホでは順位・成績・勝率ヘッダー、PCでは順位のみ */}
                      <div className="flex items-center justify-between md:justify-start md:col-span-1 border-b border-white/5 pb-2 md:border-b-0 md:pb-0">
                        <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full font-black ${
                          idx + 1 === 1 ? "bg-yellow-500/20 text-yellow-500 ring-1 ring-yellow-500/50" :
                          idx + 1 === 2 ? "bg-slate-300/20 text-slate-300 ring-1 ring-slate-300/50" :
                          idx + 1 === 3 ? "bg-amber-600/20 text-amber-500 ring-1 ring-amber-600/50" :
                          "text-slate-400"
                        }`}>
                          {idx + 1}
                        </span>
                        {/* スマホのみ表示する成績ラベル＆勝率 */}
                        <div className="flex items-center gap-2 md:hidden">
                          {team.best_result && (
                            <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ring-1 ${resultClass}`}>
                              {team.best_result}
                            </span>
                          )}
                          {team.total_matches > 0 && (
                            <div className={`px-2.5 py-0.5 rounded-md font-bold text-xs ${
                              team.win_rate >= 50 ? "bg-emerald-400/10 text-emerald-400" : "bg-amber-400/10 text-amber-400"
                            }`}>
                              勝率: {team.win_rate}%
                            </div>
                          )}
                        </div>
                      </div>

                      {/* 編成アイコン（DOMはここ1か所のみ！） */}
                      <div className="flex justify-center md:justify-start md:col-span-5 py-1 overflow-x-auto">
                        <TeamDisplay charIds={team.character_ids} allCharacters={allCharacters} />
                      </div>

                      {/* PC用: 最終成績 */}
                      <div className="hidden md:flex md:col-span-2 justify-center">
                        {team.best_result ? (
                          <span className={`inline-block px-3 py-1 text-xs font-bold rounded-full ring-1 ${resultClass}`}>
                            {team.best_result}
                          </span>
                        ) : (
                          <span className="text-slate-600 text-xs">-</span>
                        )}
                      </div>

                      {/* PC用: 勝率＆勝敗 */}
                      <div className="hidden md:flex md:col-span-2 flex-col items-end">
                        {team.total_matches > 0 ? (
                          <>
                            <span className={`text-lg font-black ${team.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                              {team.win_rate}%
                            </span>
                            <span className="text-[10px] text-slate-500 font-bold">
                              {team.win_count}W {team.total_matches - team.win_count}L
                            </span>
                          </>
                        ) : (
                          <span className="text-slate-600 text-xs">対戦なし</span>
                        )}
                      </div>

                      {/* PC用: 採用数＆率 */}
                      <div className="hidden md:flex md:col-span-2 flex-col items-end">
                        <span className="text-lg font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">
                          {team.count}
                        </span>
                        <span className="text-[10px] text-slate-500 font-bold">
                          {totalPlayers}人中 ({adoptionPct}%)
                        </span>
                      </div>

                      {/* スマホ用フッター: 採用数＆勝敗詳細 */}
                      <div className="flex md:hidden items-center justify-around text-xs text-slate-300 bg-slate-900/40 rounded-lg py-2 px-3 flex-wrap gap-y-1">
                        <div>
                          採用数: <span className="font-bold text-slate-100">{team.count}</span> 人 ({adoptionPct}%)
                        </div>
                        {team.total_matches > 0 && (
                          <>
                            <div className="w-px h-3 bg-white/10" />
                            <div>
                              勝敗: <span className="font-bold text-emerald-400">{team.win_count}W</span>
                              <span className="font-bold text-rose-400 ml-0.5">{team.total_matches - team.win_count}L</span>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}

                {(stats?.team_usage?.length ?? 0) === 0 && (
                  <div className="p-8 text-center text-slate-500 bg-slate-900/50 rounded-xl">データがありません</div>
                )}

                {(stats?.team_usage?.length ?? 0) > visibleTeamCount && (
                  <button
                    onClick={() => setVisibleTeamCount(prev => prev + 15)}
                    className="w-full py-3 mt-4 bg-slate-800/80 hover:bg-slate-700 text-slate-300 font-bold rounded-xl transition-colors ring-1 ring-white/10 shadow-lg text-sm"
                  >
                    もっと見る (残りを表示)
                  </button>
                )}
              </div>
            </section>
          </div>
        )}

        {/* WINRATE TAB */}
        {activeTab === "winrate" && stats && (
           <div className="space-y-12 animate-in fade-in zoom-in-95 duration-300">
            <section>
              <div className="flex flex-col md:flex-row md:items-center justify-between mb-6 space-y-4 md:space-y-0">
                <h2 className="text-xl font-bold text-white flex items-center space-x-2">
                  <Trophy className="text-amber-400" />
                  <span>キャラクター別勝率ランキング</span>
                </h2>
                
                {/* フィルタコントロール群 */}
                <div className="flex flex-wrap gap-2 items-center">
                  <select
                    value={winrateMinMatches}
                    onChange={(e) => setWinrateMinMatches(Number(e.target.value))}
                    className="bg-slate-800 text-slate-200 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value={1}>1戦以上</option>
                    <option value={10}>10戦以上</option>
                    <option value={30}>30戦以上</option>
                    <option value={50}>50戦以上</option>
                    <option value={100}>100戦以上</option>
                  </select>
                  <select
                    value={winrateBurstPhase}
                    onChange={(e) => setWinrateBurstPhase(e.target.value)}
                    className="bg-slate-800 text-slate-200 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">全バースト</option>
                    <option value="1">バースト1</option>
                    <option value="2">バースト2</option>
                    <option value="3">バースト3</option>
                  </select>
                  <select
                    value={winrateWeapon}
                    onChange={(e) => setWinrateWeapon(e.target.value)}
                    className="bg-slate-800 text-slate-200 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">全武器種</option>
                    <option value="AR">AR</option>
                    <option value="SMG">SMG</option>
                    <option value="SG">SG</option>
                    <option value="RL">RL</option>
                    <option value="SR">SR</option>
                    <option value="MG">MG</option>
                  </select>
                  <select
                    value={winrateElement}
                    onChange={(e) => setWinrateElement(e.target.value)}
                    className="bg-slate-800 text-slate-200 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">全属性</option>
                    <option value="灼熱">灼熱</option>
                    <option value="水冷">水冷</option>
                    <option value="風圧">風圧</option>
                    <option value="電撃">電撃</option>
                    <option value="鉄甲">鉄甲</option>
                  </select>
                  <select
                    value={winrateManufacturer}
                    onChange={(e) => setWinrateManufacturer(e.target.value)}
                    className="bg-slate-800 text-slate-200 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">全企業</option>
                    <option value="エリシオン">エリシオン</option>
                    <option value="ミシリス">ミシリス</option>
                    <option value="テトラ">テトラ</option>
                    <option value="ピルグリム">ピルグリム</option>
                    <option value="アブノーマル">アブノーマル</option>
                  </select>
                </div>
              </div>

              {/* PC表示: テーブル */}
              <div className="hidden md:block overflow-x-auto rounded-xl ring-1 ring-white/10 shadow-2xl bg-slate-900/50">
                <table className="w-full text-left border-collapse min-w-[900px]">
                  <thead>
                    <tr className="bg-slate-800/80 text-slate-400 text-sm border-b border-white/10">
                      <th className="p-4 font-medium text-center w-16">順位</th>
                      <th className="p-4 font-medium">キャラクター</th>
                      <th className="p-4 font-medium text-right w-32">勝率</th>
                      <th className="p-4 font-medium text-right w-32">戦績 (勝/敗)</th>
                      <th className="p-4 font-medium text-center w-32">最終成績</th>
                      <th className="p-4 font-medium text-right w-24">採用数</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {[...stats.character_usage]
                      .filter((e: any) => {
                        if (e.total_matches < winrateMinMatches) return false;
                        const c = allCharacters.find(char => char.id === e.id);
                        if (!c) return true;
                        
                        if (winrateBurstPhase) {
                          const charBurst = String(c.burst_phase);
                          // バースト段階が一致するか、またはバーストA（全段階対応）であれば表示
                          if (charBurst !== winrateBurstPhase && charBurst !== "A") {
                            return false;
                          }
                        }
                        if (winrateWeapon && c.weapon !== winrateWeapon) return false;
                        if (winrateElement && c.element !== winrateElement) return false;
                        if (winrateManufacturer && c.manufacturer !== winrateManufacturer) return false;
                        
                        return true;
                      })
                      .sort((a: any, b: any) => b.win_rate - a.win_rate)
                      .map((entry: any, index: number) => {
                        const c = allCharacters.find(char => char.id === entry.id) || entry;
                        const resultColors: Record<string, string> = {
                          "優勝":   "bg-amber-400/20 text-amber-300 ring-amber-400/50",
                          "準優勝": "bg-slate-300/20 text-slate-200 ring-slate-300/50",
                          "ベスト4":  "bg-orange-500/20 text-orange-400 ring-orange-500/50",
                          "ベスト8":  "bg-blue-500/20 text-blue-400 ring-blue-500/50",
                          "ベスト16": "bg-purple-500/20 text-purple-400 ring-purple-500/50",
                          "ベスト32": "bg-slate-700/60 text-slate-400 ring-slate-600/50",
                          "ベスト64": "bg-slate-800/60 text-slate-500 ring-slate-700/50",
                        };
                        const resultClass = resultColors[entry.best_result] ?? "bg-slate-800/60 text-slate-500 ring-slate-700/50";
                        return (
                          <tr key={index} className="hover:bg-white/5 transition-colors cursor-pointer group" onClick={() => setSelectedCharId(c.id)}>
                            <td className="p-4 text-center">
                              <span className="text-slate-500 font-bold">{index + 1}</span>
                            </td>
                            <td className="p-4">
                              <div className="flex items-center space-x-3">
                                <div className="w-10 h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 overflow-hidden flex items-center justify-center shrink-0">
                                  {getCharIconUrl(c) ? (
                                    <img src={getCharIconUrl(c)} loading="lazy" decoding="async" alt={c.name} className="w-full h-full object-cover" />
                                  ) : (
                                    <span className="text-[10px] text-slate-500 font-bold">{c.name.slice(0,3)}</span>
                                  )}
                                </div>
                                <span className="font-bold text-slate-200">{c.name}</span>
                              </div>
                            </td>
                            <td className="p-4 text-right">
                              <span className={`text-xl font-black ${entry.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                {entry.win_rate}%
                              </span>
                            </td>
                            <td className="p-4 text-right">
                               <div className="flex flex-col text-xs font-bold">
                                  <span className="text-emerald-400">{entry.win_count} WIN</span>
                                  <span className="text-slate-500">{entry.total_matches - entry.win_count} LOSE</span>
                               </div>
                            </td>
                            <td className="p-4 text-center">
                              {entry.best_result ? (
                                <span className={`inline-block px-3 py-1 text-xs font-bold rounded-full ring-1 ${resultClass}`}>
                                  {entry.best_result}
                                </span>
                              ) : (
                                <span className="text-slate-600 text-xs">-</span>
                              )}
                            </td>
                            <td className="p-4 text-right text-slate-400 font-bold">
                              {entry.count}
                            </td>
                          </tr>
                        );
                      })}
                    {stats.character_usage.length === 0 && (
                      <tr>
                        <td colSpan={6} className="p-8 text-center text-slate-500">データがありません</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* スマホ表示: カード型 */}
              <div className="md:hidden space-y-3">
                {[...stats.character_usage]
                  .filter((e: any) => {
                    if (e.total_matches < winrateMinMatches) return false;
                    const c = allCharacters.find(char => char.id === e.id);
                    if (!c) return true;
                    
                    if (winrateBurstPhase) {
                      const charBurst = String(c.burst_phase);
                      if (charBurst !== winrateBurstPhase && charBurst !== "A") {
                        return false;
                      }
                    }
                    if (winrateWeapon && c.weapon !== winrateWeapon) return false;
                    if (winrateElement && c.element !== winrateElement) return false;
                    if (winrateManufacturer && c.manufacturer !== winrateManufacturer) return false;
                    
                    return true;
                  })
                  .sort((a: any, b: any) => b.win_rate - a.win_rate)
                  .map((entry: any, index: number) => {
                    const c = allCharacters.find(char => char.id === entry.id) || entry;
                    const resultColors: Record<string, string> = {
                      "優勝":   "bg-amber-400/20 text-amber-300 ring-amber-400/50",
                      "準優勝": "bg-slate-300/20 text-slate-200 ring-slate-300/50",
                      "ベスト4":  "bg-orange-500/20 text-orange-400 ring-orange-500/50",
                      "ベスト8":  "bg-blue-500/20 text-blue-400 ring-blue-500/50",
                      "ベスト16": "bg-purple-500/20 text-purple-400 ring-purple-500/50",
                      "ベスト32": "bg-slate-700/60 text-slate-400 ring-slate-600/50",
                      "ベスト64": "bg-slate-800/60 text-slate-500 ring-slate-700/50",
                    };
                    const resultClass = resultColors[entry.best_result] ?? "bg-slate-800/60 text-slate-500 ring-slate-700/50";
                    return (
                      <div
                        key={index}
                        onClick={() => setSelectedCharId(c.id)}
                        className="bg-slate-800/50 hover:bg-slate-700/60 cursor-pointer transition-colors p-4 rounded-xl ring-1 ring-white/10 flex items-center justify-between gap-3"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="text-slate-500 font-bold text-base shrink-0">#{index + 1}</span>
                          <div className="w-12 h-12 rounded-lg bg-slate-800 ring-1 ring-white/10 overflow-hidden flex items-center justify-center shrink-0">
                            {getCharIconUrl(c) ? (
                              <img src={getCharIconUrl(c)} loading="lazy" decoding="async" alt={c.name} className="w-full h-full object-cover" />
                            ) : (
                              <span className="text-xs text-slate-500 font-bold">{c.name.slice(0,3)}</span>
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="font-bold text-slate-100 truncate text-base">{c.name}</div>
                            <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                              {entry.best_result && (
                                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ring-1 ${resultClass}`}>
                                  {entry.best_result}
                                </span>
                              )}
                              <span className="text-xs text-slate-400">採用: <span className="font-bold text-slate-200">{entry.count}</span></span>
                            </div>
                          </div>
                        </div>

                        <div className="text-right shrink-0">
                          <div className={`text-xl font-black ${entry.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                            {entry.win_rate}%
                          </div>
                          <div className="text-[10px] font-bold text-slate-400">
                            <span className="text-emerald-400">{entry.win_count}W</span>
                            {" / "}
                            <span className="text-rose-400">{entry.total_matches - entry.win_count}L</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                {stats.character_usage.length === 0 && (
                  <div className="p-8 text-center text-slate-500 bg-slate-900/50 rounded-xl">データがありません</div>
                )}
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
                  mode="single"
                  tournamentId={Number(id)}
                  tournamentIds={[Number(id)]} 
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
        {activeTab === "matchups" && hasFullStats && (
          <div className="space-y-8 animate-in fade-in zoom-in-95 duration-300">
            <div className="bg-purple-500/10 p-6 rounded-2xl ring-1 ring-purple-500/20">
              <label className="block text-sm font-bold text-purple-400 mb-3">分析する編成を選択</label>
              <select 
                className="w-full bg-slate-900 border border-purple-500/30 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500 mb-4"
                value={selectedTeam}
                onChange={e => setSelectedTeam(e.target.value)}
              >
                {stats.team_usage.map((team: any, idx: number) => (
                  <option key={idx} value={team.canonical_id}>
                    [{team.count}回採用] {team.characters.map((c:any) => c.id === 9999 ? '空枠' : c.name).join(" / ")}
                  </option>
                ))}
              </select>
              
              {selectedTeam && (
                <div className="pt-4 border-t border-purple-500/20 flex flex-col space-y-2">
                  <span className="text-xs font-bold text-purple-400">選択中の編成:</span>
                  <TeamDisplay charIds={stats.team_usage.find((t:any) => t.canonical_id === selectedTeam)?.character_ids || []} allCharacters={allCharacters} />
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
                    type="button"
                    onClick={() => setIsPositionStatsOpen(!isPositionStatsOpen)}
                    className="flex w-full items-center justify-between rounded-lg p-2 font-bold text-white transition-colors hover:bg-white/5"
                    aria-expanded={isPositionStatsOpen}
                  >
                    <span className="flex items-center space-x-2">
                      <span className="text-lg">📊</span>
                      <span>編成の配置ポジション分析</span>
                    </span>
                    <ChevronDown className={`h-5 w-5 text-slate-400 transition-transform ${isPositionStatsOpen ? "" : "-rotate-90"}`} />
                  </button>
                  {isPositionStatsOpen && (
                    <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-x-auto">
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
                    type="button"
                    onClick={() => setIsAdoptedPlayersOpen(!isAdoptedPlayersOpen)}
                    className="mb-2 flex w-full items-center justify-between rounded-lg p-2 font-bold text-white transition-colors hover:bg-white/5"
                    aria-expanded={isAdoptedPlayersOpen}
                  >
                    <span className="flex items-center space-x-2">
                      <UserIcon size={18} className="text-purple-400" />
                      <span>この編成を採用した指揮官</span>
                    </span>
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

            {selectedTeam && matchupDetails.length > 0 && (
              <TeamMatchupHistory
                matchupDetails={matchupDetails}
                allCharacters={allCharacters}
                onSelectCharacter={setSelectedCharId}
                onSelectOpponent={handleTeamClick}
              />
            )}

            {false && selectedTeam && matchupDetails.length > 0 && (
              <div className="space-y-4 mt-8">
                <h3 className="font-bold text-white mb-4">この編成の対戦履歴</h3>
                <div className="space-y-2">
                  {matchupDetails.map((m: any, idx: number) => (
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
                      {/* メイン行: 攻撃側を左、防衛側を右に固定 */}
                      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                        <div className="flex shrink-0 flex-col items-start space-y-1">
                          <div className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ring-1 ${
                            m.stage === "決勝" ? "bg-amber-500/20 text-amber-400 ring-amber-500/30" :
                            m.stage?.includes("準決勝") ? "bg-orange-500/20 text-orange-400 ring-orange-500/30" :
                            "bg-slate-700/50 text-slate-400 ring-slate-600/50"
                          }`}>
                            {m.stage || "不明"}
                          </div>
                        </div>
                        <div className="flex min-w-0 flex-1 flex-col items-center gap-3 sm:flex-row sm:justify-center">
                            <div className={`rounded-xl p-2 ring-1 ${m.isAttacker ? "bg-purple-500/10 ring-purple-500/40" : "ring-white/5"}`}>
                            <div className="mb-2 flex flex-wrap items-center justify-center gap-2">
                              <span className="rounded bg-blue-500/20 px-2 py-0.5 text-[10px] font-bold text-blue-400">攻撃側</span>
                              {m.isAttacker && <span className="text-[10px] font-bold text-purple-300">検索対象</span>}
                              {m.isAttacker && (
                                <span className={`text-xs font-black ${m.isWin ? "text-emerald-400" : "text-slate-500"}`}>
                                  {m.isWin ? "WIN" : "LOSE"}
                                </span>
                              )}
                            </div>
                            <SharedTeamDisplay
                              charIds={m.attackerTeam}
                              allCharacters={allCharacters}
                              collectionLevels={m.attackerCollections}
                              onCharacterClick={setSelectedCharId}
                            />
                          </div>
                          <div className="shrink-0 text-sm font-black text-slate-500">VS</div>
                          <div className={`rounded-xl p-2 ring-1 ${!m.isAttacker ? "bg-purple-500/10 ring-purple-500/40" : "ring-white/5"}`}>
                            <div className="mb-2 flex flex-wrap items-center justify-center gap-2">
                              <span className="rounded bg-red-500/20 px-2 py-0.5 text-[10px] font-bold text-red-400">防衛側</span>
                              {!m.isAttacker && <span className="text-[10px] font-bold text-purple-300">検索対象</span>}
                              {!m.isAttacker && (
                                <span className={`text-xs font-black ${m.isWin ? "text-emerald-400" : "text-slate-500"}`}>
                                  {m.isWin ? "WIN" : "LOSE"}
                                </span>
                              )}
                            </div>
                            <SharedTeamDisplay
                              charIds={m.defenderTeam}
                              allCharacters={allCharacters}
                              collectionLevels={m.defenderCollections}
                              onCharacterClick={setSelectedCharId}
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* BEST8 TAB */}
        {activeTab === "best8" && (
          <div className="space-y-8 animate-in fade-in zoom-in-95 duration-300">
            <div className="text-center mb-6">
               <h2 className="text-2xl font-black text-slate-100 flex items-center justify-center space-x-3">
                 <Trophy className="text-amber-400" size={28} />
                 <span>ベスト8進出者 編成一覧</span>
               </h2>
               <p className="text-slate-500 mt-2 text-sm italic">※ 編成をタップすると詳細分析へ遷移します</p>
            </div>

              {/* 画面幅に合わせてPCは2列、スマホは1列で表示 */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {best8Data.map((data, idx) => (
                  <section key={data.player.id || idx} className="rounded-2xl bg-slate-800/50 p-3 ring-1 ring-white/10 sm:p-4">
                    <div className="mb-3 flex items-center justify-between gap-3 border-b border-white/5 pb-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="shrink-0 text-xs font-bold text-slate-500">#{idx + 1}</span>
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-900 ring-1 ring-white/20">
                          {data.player.icon_url ? (
                            <img src={`${data.player.icon_url}?t=${Date.now()}`} alt="" className="h-full w-full object-cover" />
                          ) : (
                            <UserIcon size={20} className="text-slate-600" />
                          )}
                        </div>
                        <span className="truncate text-sm font-black text-white sm:text-base">{data.player.name}</span>
                      </div>
                      <span className={`shrink-0 rounded-full px-3 py-1 text-[10px] font-black ring-1 ${
                        data.result === "優勝" ? "bg-amber-500/20 text-amber-400 ring-amber-500/50 shadow-[0_0_15px_rgba(245,158,11,0.2)]" :
                        data.result === "準優勝" ? "bg-slate-400/20 text-slate-300 ring-slate-400/30" :
                        data.result === "ベスト4" ? "bg-orange-500/20 text-orange-400 ring-orange-500/30" :
                        "bg-slate-800 text-slate-500 ring-white/5"
                      }`}>
                        {data.result}
                      </span>
                    </div>

                    <div className="space-y-2">
                      {[1, 2, 3, 4, 5].map(teamNum => {
                        const deck = data.decks.find((d: any) => d.team_number === teamNum);
                        return (
                          <div
                            key={teamNum}
                            onClick={deck ? () => handleTeamClick(deck.canonical_id) : undefined}
                            className={`flex min-w-0 items-center gap-2 rounded-xl px-2 py-2 ring-1 ${
                              deck
                                ? "cursor-pointer bg-slate-900/50 ring-white/5 transition-colors hover:bg-slate-800/80 hover:ring-indigo-500/30"
                                : "bg-slate-900/20 text-slate-700 ring-white/[0.03]"
                            }`}
                          >
                            <span className="w-12 shrink-0 text-[10px] font-black text-slate-400">TEAM {teamNum}</span>
                            <div className="min-w-0 flex-1 overflow-x-auto py-1">
                              {deck ? (
                                <SharedTeamDisplay
                                  charIds={deck.character_ids}
                                  allCharacters={allCharacters}
                                  collectionLevels={deck.collection_levels}
                                  onCharacterClick={setSelectedCharId}
                                />
                              ) : (
                                <span className="text-xs italic">未登録</span>
                              )}
                            </div>
                            {deck && (
                              <div className="ml-auto flex w-20 shrink-0 flex-col items-end border-l border-white/10 pl-2 text-right">
                                <div className="flex items-center gap-1.5 whitespace-nowrap text-[10px] font-bold">
                                  <span className="text-emerald-400">{deck.wins}勝</span>
                                  <span className="text-slate-500">{deck.losses}敗</span>
                                </div>
                                <span className={`mt-0.5 text-sm font-black ${
                                  deck.win_rate >= 50 ? "text-emerald-400" : "text-orange-400"
                                }`}>
                                  {deck.win_rate}%
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </section>
                ))}
              </div>

              {false && (<>
              {/* 旧レイアウト（移行確認後に削除予定） */}
              <div className="hidden overflow-x-auto rounded-2xl ring-1 ring-white/10 shadow-2xl bg-slate-900/50">
                <table className="w-full text-left border-collapse min-w-[1200px]">
                  <thead>
                    <tr className="bg-slate-800/80 text-slate-400 text-[10px] uppercase tracking-wider border-b border-white/10">
                      <th className="p-4 font-black text-center w-24">項目</th>
                      {best8Data.map((data, idx) => (
                        <th key={idx} className="p-4 font-black text-center border-l border-white/5">
                          Player {idx + 1}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {/* Player Name Row */}
                    <tr className="bg-blue-500/5">
                      <td className="p-4 font-bold text-slate-400 text-center bg-slate-800/30">名前</td>
                      {best8Data.map((data, idx) => (
                        <td key={idx} className="p-4 text-center border-l border-white/5">
                          <div className="flex flex-col items-center space-y-2">
                            <div className="w-10 h-10 rounded-full bg-slate-900 ring-1 ring-white/20 overflow-hidden flex items-center justify-center">
                              {data.player.icon_url ? (
                                <img src={`${data.player.icon_url}?t=${Date.now()}`} alt="Icon" className="w-full h-full object-cover" />
                              ) : (
                                <UserIcon size={20} className="text-slate-600" />
                              )}
                            </div>
                            <span className="font-black text-white text-sm whitespace-nowrap">{data.player.name}</span>
                          </div>
                        </td>
                      ))}
                    </tr>
                    
                    {/* Result Row */}
                    <tr className="bg-slate-800/20">
                      <td className="p-4 font-bold text-slate-400 text-center bg-slate-800/30">成績</td>
                      {best8Data.map((data, idx) => (
                        <td key={idx} className="p-4 text-center border-l border-white/5">
                          <div className={`px-3 py-1 rounded-full text-[10px] font-black inline-block ring-1 ${
                            data.result === "優勝" ? "bg-amber-500/20 text-amber-400 ring-amber-500/50 shadow-[0_0_15px_rgba(245,158,11,0.2)]" :
                            data.result === "準優勝" ? "bg-slate-400/20 text-slate-300 ring-slate-400/30" :
                            data.result === "ベスト4" ? "bg-orange-500/20 text-orange-400 ring-orange-500/30" :
                            "bg-slate-800 text-slate-500 ring-white/5"
                          }`}>
                            {data.result}
                          </div>
                        </td>
                      ))}
                    </tr>
                    
                    {/* Deck Rows 1-5 */}
                    {[1, 2, 3, 4, 5].map(teamNum => (
                      <tr key={teamNum} className="hover:bg-white/[0.02] transition-colors">
                        <td className="p-4 font-bold text-slate-500 text-center bg-slate-800/30">
                          <div className="flex flex-col items-center">
                            <span className="text-[10px] opacity-50 uppercase tracking-tighter">Team</span>
                            <span className="text-lg font-black">{teamNum}</span>
                          </div>
                        </td>
                        {best8Data.map((data, idx) => {
                          const deck = data.decks.find((d: any) => d.team_number === teamNum);
                          return (
                            <td key={idx} className="p-4 border-l border-white/5 align-middle">
                              {deck ? (
                                <div 
                                  onClick={() => handleTeamClick(deck.canonical_id)}
                                  className="hover:bg-slate-800/50 p-2 rounded-xl transition-all cursor-pointer ring-1 ring-transparent hover:ring-indigo-500/30 hover:shadow-lg group flex justify-center"
                                >
                                  <SharedTeamDisplay
                                    charIds={deck.character_ids}
                                    allCharacters={allCharacters}
                                    collectionLevels={deck.collection_levels}
                                    onCharacterClick={setSelectedCharId}
                                  />
                                </div>
                              ) : (
                                <div className="flex items-center justify-center h-16 text-slate-700 italic text-xs">
                                  未登録
                                </div>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* スマホ表示: カード型 */}
              <div className="hidden space-y-4">
                {best8Data.map((data, idx) => (
                  <div key={idx} className="bg-slate-800/50 rounded-2xl ring-1 ring-white/10 p-4 space-y-4">
                    <div className="flex items-center justify-between border-b border-white/5 pb-3">
                      <div className="flex items-center space-x-3">
                        <span className="text-xs font-bold text-slate-500">#{idx + 1}</span>
                        <div className="w-10 h-10 rounded-full bg-slate-900 ring-1 ring-white/20 overflow-hidden flex items-center justify-center shrink-0">
                          {data.player.icon_url ? (
                            <img src={`${data.player.icon_url}?t=${Date.now()}`} alt="Icon" className="w-full h-full object-cover" />
                          ) : (
                            <UserIcon size={20} className="text-slate-600" />
                          )}
                        </div>
                        <span className="font-black text-white text-base">{data.player.name}</span>
                      </div>
                      <div className={`px-3 py-1 rounded-full text-xs font-black inline-block ring-1 ${
                        data.result === "優勝" ? "bg-amber-500/20 text-amber-400 ring-amber-500/50 shadow-[0_0_15px_rgba(245,158,11,0.2)]" :
                        data.result === "準優勝" ? "bg-slate-400/20 text-slate-300 ring-slate-400/30" :
                        data.result === "ベスト4" ? "bg-orange-500/20 text-orange-400 ring-orange-500/30" :
                        "bg-slate-800 text-slate-500 ring-white/5"
                      }`}>
                        {data.result}
                      </div>
                    </div>

                    <div className="space-y-3">
                      {[1, 2, 3, 4, 5].map(teamNum => {
                        const deck = data.decks.find((d: any) => d.team_number === teamNum);
                        if (!deck) return null;
                        return (
                          <div
                            key={teamNum}
                            onClick={() => handleTeamClick(deck.canonical_id)}
                            className="bg-slate-900/50 hover:bg-slate-800/80 p-3 rounded-xl transition-all cursor-pointer ring-1 ring-white/5 flex items-center justify-between gap-2"
                          >
                            <span className="text-xs font-black text-slate-400 shrink-0 w-16">Team {teamNum}</span>
                            <div className="flex justify-center overflow-x-auto py-1">
                              <SharedTeamDisplay
                                charIds={deck.character_ids}
                                allCharacters={allCharacters}
                                collectionLevels={deck.collection_levels}
                                onCharacterClick={setSelectedCharId}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
              </>)}
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
                      {getCharIconUrl(c) ? (
                         <img src={getCharIconUrl(c)} loading="lazy" decoding="async" alt={c.name} className="w-full h-full object-cover" />
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
                    mode="single"
                    tournamentId={Number(id)}
                    tournamentIds={[Number(id)]} 
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
                aria-label="閉じる"
              >
                <X size={20} />
              </button>
            </div>
            {(() => {
              const c = allCharacters.find(x => x.id === selectedCharId);
              if (!c) return null;
              
              const usageData = stats?.character_usage?.find((x:any) => x.id === selectedCharId);
              const usageCount = usageData?.count || 0;
              const winRate = usageData?.win_rate || 0;
              const charWins = usageData?.win_count || 0;
              const totalMatches = usageData?.total_matches || 0;
              const charLosses = totalMatches - charWins;
              const relatedTeams = stats?.team_usage?.filter((t:any) => t.character_ids.includes(selectedCharId)) || [];

              const synergyCounts: Record<number, number> = {};
              relatedTeams.forEach((t: any) => {
                t.character_ids.forEach((cid: number) => {
                  if (cid !== selectedCharId) {
                    synergyCounts[cid] = (synergyCounts[cid] || 0) + t.count;
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
                          レアリティ: {c.rarity || "不明"}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center self-start sm:self-auto">
                      <Link
                        href={`/tournament/${id}/dashboard/character/${selectedCharId}`}
                        className="flex items-center space-x-1.5 px-4 py-2 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-xl text-sm font-bold ring-1 ring-blue-500/30 transition-all whitespace-nowrap"
                        onClick={() => setSelectedCharId(null)}
                      >
                        <span>📄</span>
                        <span>フルページで詳細を見る</span>
                      </Link>
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
                  {usageData?.position_stats && (
                    <div className="space-y-3">
                      <h3 className="font-bold text-white flex items-center space-x-2">
                        <span className="text-lg">📊</span>
                        <span>部隊内の配置傾向</span>
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
                  {usageData?.team_position_stats && (
                    <div className="space-y-3">
                      <h3 className="font-bold text-white flex items-center space-x-2">
                        <span className="text-lg">📊</span>
                        <span>編成の配置傾向</span>
                      </h3>
                      <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-x-auto">
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
                                {getCharIconUrl(ch) ? (
                                  <img src={getCharIconUrl(ch)} loading="lazy" decoding="async" alt={ch.name} className="w-full h-full object-cover" />
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
                                {getCharIconUrl(ch) ? (
                                  <img src={getCharIconUrl(ch)} loading="lazy" decoding="async" alt={ch.name} className="w-full h-full object-cover" />
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
                                {getCharIconUrl(ch) ? (
                                  <img src={getCharIconUrl(ch)} loading="lazy" decoding="async" alt={ch.name} className="w-full h-full object-cover" />
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
                              <TeamDisplay charIds={team.character_ids} allCharacters={allCharacters} />
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
