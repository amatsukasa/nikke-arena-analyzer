"use client";
export const dynamic = 'force-dynamic';
import { useState, useRef, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ChevronLeft, ShieldAlert, Trophy, Swords, BarChart3 } from "lucide-react";
import Link from "next/link";
import ChampionTournamentRegistrationShell from "../../../components/ChampionTournamentRegistrationShell";
import DeckRegistrationEditor from "../../../components/DeckRegistrationEditor";
import DeckRegistrationViewer from "../../../components/DeckRegistrationViewer";
import PlayerIconEditor from "../../../components/PlayerIconEditor";
import TournamentPlayerPill from "../../../components/TournamentPlayerPill";
import MatchResultEditor from "../../../components/MatchResultEditor";
import { useAuth } from "../../../context/AuthContext";
import { apiErrorMessage, normalizeTournament, TournamentSummary } from "../../../lib/tournaments";
import { prepareAnalysisImage } from "../../../lib/deckImagePreparation";
import { hasCompleteRegistrationStructure, normalizeAnalyzedRegistrationTeams, normalizeSavedRegistrationTeams, registrationSaveConfirmation, registrationTeamsPayload, validateRegistrationTeams } from "../../../lib/deckRegistration";
import { full64MatchPayload, MatchEditorResult, normalizeFull64MatchAnalysis } from "../../../lib/matchRegistration";

export default function TournamentDetailRouter() {
  const params = useParams();
  const { user, isLoading: authLoading } = useAuth();
  const tournamentId = Number(params.id);
  const [tournament, setTournament] = useState<TournamentSummary | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!Number.isInteger(tournamentId) || tournamentId <= 0) {
      setLoadError("大会IDが正しくありません。");
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setLoadError("");
    fetch(`/api/tournaments/${tournamentId}`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(apiErrorMessage(data, "大会情報の取得に失敗しました。"));
        setTournament(normalizeTournament(data));
      })
      .catch(error => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setLoadError(error instanceof Error ? error.message : "大会情報の取得に失敗しました。");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [tournamentId]);

  if (loading || authLoading) {
    return <div className="loading-screen min-h-[50vh]"><div className="spinner" /><p>大会情報を読み込み中...</p></div>;
  }
  if (loadError || !tournament) {
    return <main className="mx-auto max-w-3xl p-6"><div role="alert" className="rounded-xl border border-red-800 bg-red-950/40 p-4 text-red-300">{loadError || "大会情報が見つかりません。"}</div></main>;
  }
  if (tournament.registration_scope === "champion_8") {
    const canEdit = Boolean(user && (user.role === "admin" || user.id === tournament.created_by || user.email === tournament.creator_email));
    return (
      <ChampionTournamentRegistrationShell
        tournamentId={tournament.id}
        publicationStatus={tournament.publication_status}
        providerGameStartDate={tournament.provider_game_start_date}
        canEdit={canEdit}
      />
    );
  }
  const canEdit = Boolean(user && (user.role === "admin" || user.id === tournament.created_by || user.email === tournament.creator_email));
  return <Full64TournamentDetail canEdit={canEdit} />;
}

function Full64TournamentDetail({ canEdit }: { canEdit: boolean }) {
  const params = useParams();
  const id = params.id;
  const router = useRouter();
  const formRef = useRef<HTMLDivElement>(null);
  const seedFieldRef = useRef<HTMLDivElement>(null);

  const [seed, setSeed] = useState(1);
  const [isUploading, setIsUploading] = useState(false);
  const [characters, setCharacters] = useState<any[]>([]);
  const [selectedTeams, setSelectedTeams] = useState<any[]>([]);

  // 勝敗登録用state
  const [mode, setMode] = useState<"deck" | "match">("deck");
  const [attackerSeed, setAttackerSeed] = useState(1);
  const [defenderSeed, setDefenderSeed] = useState(2);
  const [matchStage, setMatchStage] = useState("Groups");
  const [full64MatchTeams,setFull64MatchTeams]=useState<{attacker:any[];defender:any[]}>({attacker:[],defender:[]});
  const [full64MatchDirty,setFull64MatchDirty]=useState(false);

  // フォーム用プレイヤー情報
  const [formPlayerIcon, setFormPlayerIcon] = useState("");
  const [registeredDecks, setRegisteredDecks] = useState<any[]>([]);
  const [isLoadingRegisteredDecks, setIsLoadingRegisteredDecks] = useState(false);
  const [deckScreen, setDeckScreen] = useState<"view" | "edit">("edit");
  const [deckDirty, setDeckDirty] = useState(false);

  const [isUploadingIcon, setIsUploadingIcon] = useState(false);

  // トーナメント表データ
  const [bracketData, setBracketData] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<number | "champion">(1);

  const [tournamentId, setTournamentId] = useState<number | null>(null);

  const fetchBracket = async () => {
    if (!tournamentId) return;
    const res = await fetch(`/api/tournaments/${tournamentId}/bracket`);
    const data = await res.json();
    setBracketData(data);
  };

  useEffect(() => {
    if (id) {
      setTournamentId(parseInt(id as string));
    }
  }, [id]);

  useEffect(() => {
    fetch("/api/characters").then(r => r.json()).then(setCharacters);
  }, []);

  useEffect(() => {
    if (tournamentId) {
      fetchBracket();
    }
  }, [tournamentId]);

  const loadPlayerDetails = async (targetSeed = seed) => {
    if (!tournamentId) return;
    setIsLoadingRegisteredDecks(true);
    try {
      const response = await fetch(`/api/tournaments/${tournamentId}/players/${targetSeed}/details`);
      const data = await response.json();
      const iconUrl = data.player?.icon_url;
      setFormPlayerIcon(iconUrl ? `${iconUrl}?t=${Date.now()}` : "");
      const savedTeams = normalizeSavedRegistrationTeams(data);
      setRegisteredDecks(data.decks || []);
      setSelectedTeams(savedTeams);
      setDeckScreen(hasCompleteRegistrationStructure(savedTeams) ? "view" : "edit");
      setDeckDirty(false);
    } catch {
      setFormPlayerIcon("");
      setRegisteredDecks([]);
      setSelectedTeams([]);
      setDeckScreen("edit");
      setDeckDirty(false);
    } finally {
      setIsLoadingRegisteredDecks(false);
    }
  };

  // シード番号変更時に既存のプレイヤー情報と編成を取得
  useEffect(() => {
    if (mode === "deck" && tournamentId) {
      loadPlayerDetails(seed);
    }
  }, [seed, mode, tournamentId]);
  useEffect(()=>{if(mode!=="match"||!tournamentId)return;const controller=new AbortController();Promise.all([attackerSeed,defenderSeed].map(async playerSeed=>{const response=await fetch(`/api/tournaments/${tournamentId}/players/${playerSeed}/details`,{cache:"no-store",signal:controller.signal});if(!response.ok)return [];return normalizeSavedRegistrationTeams(await response.json());})).then(([attacker,defender])=>setFull64MatchTeams({attacker,defender})).catch(error=>{if(!(error instanceof DOMException&&error.name==="AbortError"))setFull64MatchTeams({attacker:[],defender:[]});});return()=>controller.abort();},[mode,tournamentId,attackerSeed,defenderSeed]);

  const seeds = Array.from({ length: 64 }, (_, i) => i + 1);

  const handlePlayerClick = (s: number) => {
    if (mode==="match"&&full64MatchDirty&&!window.confirm("未保存の勝敗入力を破棄してPlayer登録へ移動しますか？")) return;
    setFull64MatchDirty(false);
    setMode("deck");
    setSeed(s);
    if (s === seed) void loadPlayerDetails(s);
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const editFull64PlayerInfo = () => {
    setDeckScreen("edit");
    window.requestAnimationFrame(() => seedFieldRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const handlePairClick = (s1: number, s2: number, stage: string) => {
    if (mode==="match"&&full64MatchDirty&&!window.confirm("未保存の勝敗入力を破棄して別の試合へ移動しますか？")) return;
    setFull64MatchDirty(false);
    setMode("match");
    setAttackerSeed(s1);
    setDefenderSeed(s2);
    setMatchStage(stage);
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const analyzeFull64Teams = async (preparedImages: { file: File; preCropped: boolean }[]) => {
    if (!tournamentId) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append("tournament_id", tournamentId.toString());
    formData.append("seed_number", seed.toString());
    preparedImages.forEach(({ file, preCropped }) => {
      formData.append("images", file);
      formData.append("image_pre_cropped", preCropped ? "true" : "false");
    });
    try {
      const response = await fetch("/api/analyze/deck", { method: "POST", body: formData });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.detail || "画像解析に失敗しました。");
      setSelectedTeams(normalizeAnalyzedRegistrationTeams(data));
      setDeckScreen("edit");
      setDeckDirty(true);
    } finally {
      setIsUploading(false);
    }
  };

  const handleSave = async () => {
    const issues = validateRegistrationTeams(selectedTeams, new Set(characters.map(character => character.id)));
    if (issues.length) { alert(issues.join("\n")); return; }
    const names = new Map<number,string>(characters.map(character => [character.id, character.name]));
    if (!window.confirm(registrationSaveConfirmation(`Player ${seed}`, `シード${seed}`, selectedTeams, names, registeredDecks.length > 0))) return;

    if (!tournamentId) return;
    try {
      const res = await fetch(`/api/tournaments/${tournamentId}/teams`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          seed_number: seed,
          teams: registrationTeamsPayload(selectedTeams),
          player_icon_url: formPlayerIcon ? formPlayerIcon.split("?")[0] : null
        })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.is_update) {
          alert("既存の編成データを上書きしました！（古いデータは自動削除済み）");
        } else {
          alert("編成データを保存しました！");
        }
        if (registeredDecks.length > 0) {
          await loadPlayerDetails(seed);
          setDeckScreen("view");
          setDeckDirty(false);
        } else {
          setSeed(prev => prev < 64 ? prev + 1 : 1);
          window.requestAnimationFrame(() => seedFieldRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
        }
        fetchBracket();
      } else {
        alert("保存に失敗しました。");
      }
    } catch (err) {
      alert("エラーが発生しました。");
    }
  };

  const uploadFull64PlayerIcon = async (file: File) => {
    if (!tournamentId) throw new Error("大会IDが確定していません。");
    setIsUploadingIcon(true);
    try {
      const formData = new FormData();
      formData.append("image", file, "avatar.png");
      formData.append("tournament_id", String(tournamentId));
      formData.append("seed_number", String(seed));
      const response = await fetch("/api/upload/player-icon", { method: "POST", body: formData, credentials: "include" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.detail || `アップロードに失敗しました (HTTP ${response.status})`);
      setFormPlayerIcon(`${data.url}?t=${Date.now()}`);
      await loadPlayerDetails(seed);
      await fetchBracket();
    } finally {
      setIsUploadingIcon(false);
    }
  };

  // ------------------
  // Bracket UI Components
  // ------------------

  // プレイヤーのアイコンURLを取得
  const getPlayerIconUrl = (player: any) => {
    if (!player) return null;
    const bust = `?t=${Date.now()}`;
    if (player.icon_url) return player.icon_url.includes("?") ? player.icon_url : player.icon_url + bust;
    return null;
  };

  const getPlayerBySeed = (seedNum: number) => {
    if (!bracketData || !bracketData.groups) return null;
    for (const group of bracketData.groups) {
      const p = group.players.find((p: any) => p && (p.original_seed === seedNum || p.seed === seedNum));
      if (p && p.id) return p;
    }
    return null;
  };

  const PlayerCard = ({ player, isWinner = false, align = "left", scale = 1 }: { player: any, isWinner?: boolean, align?: "left" | "right" | "center", scale?: number }) => {
    if (!player) return null;
    const iconUrl = getPlayerIconUrl(player);
    const isUnknown = !player.id && player.name === "未確定";
    return <TournamentPlayerPill name={player.name} eyebrow={`SEED ${player.seed}`} iconUrl={iconUrl} align={align} scale={scale} winner={isWinner} selected={mode==="deck"&&(player.original_seed||player.seed)===seed} disabled={isUnknown} onClick={()=>handlePlayerClick(player.original_seed||player.seed)}/>;
  };

  const analyzeFull64Match = async (file: File): Promise<MatchEditorResult> => {
    if (!tournamentId) throw new Error("大会IDが確定していません。");
    setIsUploading(true);
    try {
      const prepared = await prepareAnalysisImage(file, { maxOutputWidth: 1080, filenameSuffix: ".match-modal.png" });
      const ratio = file.size > 0 ? prepared.file.size / file.size : 1;
      const upload = prepared.preCropped && ratio <= 1.2 ? prepared.file : file;
      const body = new FormData(); body.append("tournament_id",String(tournamentId)); body.append("attacker_seed",String(attackerSeed)); body.append("defender_seed",String(defenderSeed)); body.append("stage",matchStage); body.append("image",upload);
      const response = await fetch("/api/analyze/match_result",{method:"POST",body}); const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data?.detail||"解析エラーが発生しました。");
      return normalizeFull64MatchAnalysis(data);
    } finally { setIsUploading(false); }
  };

  const saveFull64Match = async (result: MatchEditorResult) => {
    if (!tournamentId) return;
    const payload=full64MatchPayload(result,tournamentId,matchStage,attackerSeed,defenderSeed);
    const response=await fetch(`/api/tournaments/${tournamentId}/matches`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    if(!response.ok)throw new Error("保存に失敗しました。両プレイヤーの編成が登録されている必要があります。");
    window.alert("勝敗データを保存しました！"); await fetchBracket(); window.scrollTo({top:0,behavior:"smooth"});
  };

  const MatchCard = ({ p1, p2, winner, label, scale = 1, align = "left" }: { p1: any, p2: any, winner: any, label: string, scale?: number, align?: "left" | "right" | "center" }) => {
    const isReady = p1 && p2 && p1.id && p2.id;
    const isResolved = !!winner?.id;
    const iconUrl = isResolved ? getPlayerIconUrl(winner) : null;

    return (
      <div
        onClick={() => { if (isReady) handlePairClick(p1.original_seed || p1.seed, p2.original_seed || p2.seed, label); }}
        className={`group relative z-30 flex items-center gap-2 p-1.5 rounded-full border transition-all backdrop-blur-md ${isReady ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'} ${isResolved ? 'bg-slate-900/90 border-amber-400 shadow-[0_0_15px_rgba(251,191,36,0.3)]' : 'bg-slate-900/60 border-slate-700 border-dashed'} ${align === 'right' ? 'flex-row-reverse' : ''}`}
        style={{ transform: `scale(${scale})` }}
      >
        <div className={`relative w-10 h-10 rounded-full shrink-0 border-2 overflow-hidden flex items-center justify-center ${isResolved ? 'border-amber-400 bg-slate-800' : 'border-slate-700 bg-slate-900'}`}>
          {iconUrl ? (
            <img src={iconUrl} alt="icon" className="w-full h-full object-cover" />
          ) : (
            <span className="text-[10px] font-black text-blue-500 italic">VS</span>
          )}
          {isResolved && (
            <div className="absolute -top-1 -right-1 bg-amber-500 text-white rounded-full p-0.5 shadow">
              <Trophy size={10} />
            </div>
          )}
        </div>

        <div className={`flex flex-col justify-center px-2 min-w-[80px] max-w-[100px] ${align === 'right' ? 'items-end text-right' : 'items-start text-left'}`}>
          <div className="text-[10px] text-slate-400 font-bold tracking-wider">{isResolved ? `SEED ${winner.seed}` : label}</div>
          <div className={`text-xs font-black truncate w-full ${isResolved ? 'text-amber-400' : 'text-slate-500 italic'}`}>{isResolved ? winner.name : "未確定"}</div>
        </div>

        {isReady && (
          <div className="absolute inset-0 flex items-center justify-center bg-blue-600/90 rounded-full opacity-0 group-hover:opacity-100 transition-all z-40">
            <span className="text-white text-[10px] font-black px-2 text-center leading-tight">{isResolved ? "結果を修正" : "勝敗を登録"}</span>
          </div>
        )}
      </div>
    );
  };

  const OrthogonalLine = ({ x1, y1, x2, y2, color = "#3b82f6" }: { x1: number, y1: number, x2: number, y2: number, color?: string }) => {
    const midX = x1 + (x2 - x1) * 0.5;
    const d = `M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`;

    return (
      <svg className="absolute inset-0 w-full h-full pointer-events-none z-10" viewBox="0 0 100 100" preserveAspectRatio="none" style={{ overflow: 'visible' }}>
        <path d={d} fill="none" stroke={color} strokeWidth="0.3" strokeOpacity="0.6" strokeLinejoin="round" />
      </svg>
    );
  };

  const BracketTree = ({ bracket, isChampion = false }: { bracket: any, isChampion?: boolean }) => {
    const { players, qf_winners, sf_winners, winner } = bracket;
    const getP = (pid: number | null) => {
      if (!pid) return { id: null, name: "未確定", seed: "?" };
      return players.find((p: any) => p.id === pid) || { id: null, name: "未確定", seed: "?" };
    };

    const p1 = players[0]; const p2 = players[1];
    const p3 = players[2]; const p4 = players[3];
    const p5 = players[4]; const p6 = players[5];
    const p7 = players[6]; const p8 = players[7];

    const qw1 = getP(qf_winners[0]); const qw2 = getP(qf_winners[1]);
    const qw3 = getP(qf_winners[2]); const qw4 = getP(qf_winners[3]);
    const sw1 = getP(sf_winners[0]); const sw2 = getP(sf_winners[1]);
    const fw = getP(winner);

    const LX = 15; const MX = 32; const CX = 50; const RX = 85; const RMX = 68;
    const Y1 = 12; const Y2 = 28; const Y3 = 72; const Y4 = 88;
    const YM1 = 20; const YM2 = 80; const YS1 = 35; const YS2 = 65; const YF = 50;

    return (
      <div className="relative w-full aspect-[9/16] md:aspect-[3/4] lg:aspect-square max-w-4xl mx-auto bg-slate-950/50 rounded-3xl overflow-hidden border border-white/5 p-4 shadow-inner">
        <div className="absolute inset-0 opacity-10 pointer-events-none flex items-center justify-center"><Trophy size={400} className="text-blue-500 blur-3xl" /></div>
        <div className="absolute top-2 left-1/2 -translate-x-1/2 text-center z-10 w-full">
          <div className="text-xs md:text-sm text-blue-400 font-bold tracking-widest">{isChampion ? "CHAMPION FINALS" : "GROUP QUALIFIERS"}</div>
          <div className="text-xl md:text-3xl font-black text-slate-100 uppercase tracking-widest">{isChampion ? "チャンピオン対抗戦" : "進級戦"}</div>
        </div>

        {/* --- Lines --- */}
        <OrthogonalLine x1={LX} y1={Y1} x2={MX} y2={YM1} />
        <OrthogonalLine x1={LX} y1={Y2} x2={MX} y2={YM1} />
        <OrthogonalLine x1={LX} y1={Y3} x2={MX} y2={YM2} />
        <OrthogonalLine x1={LX} y1={Y4} x2={MX} y2={YM2} />
        <OrthogonalLine x1={RX} y1={Y1} x2={RMX} y2={YM1} />
        <OrthogonalLine x1={RX} y1={Y2} x2={RMX} y2={YM1} />
        <OrthogonalLine x1={RX} y1={Y3} x2={RMX} y2={YM2} />
        <OrthogonalLine x1={RX} y1={Y4} x2={RMX} y2={YM2} />

        <OrthogonalLine x1={MX} y1={YM1} x2={CX} y2={YS1} />
        <OrthogonalLine x1={RMX} y1={YM1} x2={CX} y2={YS1} />
        <OrthogonalLine x1={MX} y1={YM2} x2={CX} y2={YS2} />
        <OrthogonalLine x1={RMX} y1={YM2} x2={CX} y2={YS2} />

        <OrthogonalLine x1={CX} y1={YS1} x2={CX} y2={YF} color="#fbbf24" />
        <OrthogonalLine x1={CX} y1={YS2} x2={CX} y2={YF} color="#fbbf24" />

        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-20" style={{ left: `${LX}%`, top: `${Y1}%` }}><PlayerCard player={p1} align="left" scale={0.75} /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-20" style={{ left: `${LX}%`, top: `${Y2}%` }}><PlayerCard player={p2} align="left" scale={0.75} /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-20" style={{ left: `${LX}%`, top: `${Y3}%` }}><PlayerCard player={p5} align="left" scale={0.75} /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-20" style={{ left: `${LX}%`, top: `${Y4}%` }}><PlayerCard player={p6} align="left" scale={0.75} /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-20" style={{ left: `${RX}%`, top: `${Y1}%` }}><PlayerCard player={p3} align="right" scale={0.75} /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-20" style={{ left: `${RX}%`, top: `${Y2}%` }}><PlayerCard player={p4} align="right" scale={0.75} /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-20" style={{ left: `${RX}%`, top: `${Y3}%` }}><PlayerCard player={p7} align="right" scale={0.75} /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-20" style={{ left: `${RX}%`, top: `${Y4}%` }}><PlayerCard player={p8} align="right" scale={0.75} /></div>

        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-30" style={{ left: `${MX}%`, top: `${YM1}%` }}><MatchCard p1={p1} p2={p2} winner={qw1} label={isChampion ? "Best 8" : "Best 64"} scale={0.85} align="left" /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-30" style={{ left: `${RMX}%`, top: `${YM1}%` }}><MatchCard p1={p3} p2={p4} winner={qw2} label={isChampion ? "Best 8" : "Best 64"} scale={0.85} align="right" /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-30" style={{ left: `${MX}%`, top: `${YM2}%` }}><MatchCard p1={p5} p2={p6} winner={qw3} label={isChampion ? "Best 8" : "Best 64"} scale={0.85} align="left" /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-30" style={{ left: `${RMX}%`, top: `${YM2}%` }}><MatchCard p1={p7} p2={p8} winner={qw4} label={isChampion ? "Best 8" : "Best 64"} scale={0.85} align="right" /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-30" style={{ left: `${CX}%`, top: `${YS1}%` }}><MatchCard p1={qw1} p2={qw2} winner={sw1} label={isChampion ? "Best 4" : "Best 32"} scale={1.0} align="left" /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-30" style={{ left: `${CX}%`, top: `${YS2}%` }}><MatchCard p1={qw3} p2={qw4} winner={sw2} label={isChampion ? "Best 4" : "Best 32"} scale={1.0} align="right" /></div>
        <div className="absolute -translate-x-1/2 -translate-y-1/2 z-40" style={{ left: `${CX}%`, top: `${YF}%` }}>
          <div className="relative group">
            <div className="absolute inset-0 bg-amber-500 blur-2xl opacity-40 rounded-full animate-pulse"></div>
            <MatchCard p1={sw1} p2={sw2} winner={fw} label={isChampion ? "FINAL" : "Best 16"} scale={1.2} align="center" />
          </div>
        </div>
      </div>
    );
  };



  return (
    <main className="p-4 md:p-8 max-w-7xl mx-auto space-y-8 pb-32">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-4">
          <Link href="/tournaments/manage" aria-label="大会一覧に戻る">
            <div className="p-2 bg-white/5 hover:bg-white/10 rounded-full transition-colors cursor-pointer">
              <ChevronLeft size={24} className="text-slate-400" />
            </div>
          </Link>
          <h1 className="text-2xl md:text-3xl font-black text-slate-100">トーナメント表</h1>
        </div>
        <div className="flex items-center space-x-3">
          <Link
            href={`/tournament/${id}/dashboard`}
            className="flex items-center space-x-2 px-4 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-xl font-bold shadow-lg shadow-blue-500/20 transition-all text-sm ring-1 ring-white/10"
          >
            <span>📊</span>
            <span>この大会の分析を見る（メンバー専用）</span>
          </Link>
        </div>
      </div>

      {/* Bracket View Area */}
      <div className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 rounded-3xl shadow-2xl overflow-hidden">
        {/* Tabs */}
        <div className="flex overflow-x-auto border-b border-white/10 bg-slate-950/80 scrollbar-hide">
          {[1, 2, 3, 4, 5, 6, 7, 8].map(t => (
            <button
              key={t}
              onClick={() => setActiveTab(t)}
              className={`px-4 md:px-6 py-4 font-bold text-xs md:text-sm whitespace-nowrap transition-colors border-b-2 ${activeTab === t ? 'border-blue-500 text-blue-400 bg-blue-500/10' : 'border-transparent text-slate-500 hover:text-slate-300 hover:bg-white/5'}`}
            >
              タブ {String(t).padStart(2, '0')}
            </button>
          ))}
          <button
            onClick={() => setActiveTab("champion")}
            className={`px-4 md:px-6 py-4 font-black text-xs md:text-sm whitespace-nowrap transition-colors border-b-2 flex items-center space-x-2 ${activeTab === "champion" ? 'border-amber-500 text-amber-400 bg-amber-500/10' : 'border-transparent text-amber-600/70 hover:text-amber-500 hover:bg-white/5'}`}
          >
            <Trophy size={16} />
            <span>チャンピオン対抗戦</span>
          </button>
        </div>

        {/* Bracket Content */}
        <div className="p-4 md:p-8 bg-slate-900">
          {!bracketData ? (
            <div className="flex justify-center items-center h-[600px]">
              <div className="animate-spin w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full" />
            </div>
          ) : activeTab === "champion" ? (
            <BracketTree bracket={bracketData.champion_finals} isChampion={true} />
          ) : (
            <BracketTree bracket={bracketData.groups[activeTab as number - 1]} isChampion={false} />
          )}
        </div>
      </div>

      {/* Upload Form Area */}
      <div ref={formRef} className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-6 rounded-3xl shadow-2xl flex flex-col mt-12 scroll-mt-24">
        <h2 className="text-2xl font-black mb-6 text-center text-slate-200">データ登録フォーム</h2>

        {/* Mode Switcher */}
        <div className="flex bg-slate-800 p-1 rounded-xl mb-6 ring-1 ring-white/5 max-w-md mx-auto w-full">
          <button
            onClick={() => {if(mode==="match"&&full64MatchDirty&&!window.confirm("未保存の勝敗入力を破棄して編成登録へ移動しますか？"))return;setFull64MatchDirty(false);setMode("deck");}}
            className={`flex-1 py-3 text-sm font-bold rounded-lg transition-all ${mode === "deck" ? "bg-blue-500 text-white shadow" : "text-slate-400 hover:text-slate-300"}`}
          >
            編成の登録
          </button>
          <button
            onClick={() => setMode("match")}
            className={`flex-1 py-3 text-sm font-bold rounded-lg transition-all ${mode === "match" ? "bg-emerald-500 text-white shadow" : "text-slate-400 hover:text-slate-300"}`}
          >
            勝敗結果の登録
          </button>
        </div>

        <div className="max-w-2xl mx-auto w-full">
          {mode === "deck" ? (
            <div className="space-y-6">
              <div ref={seedFieldRef} className="scroll-mt-24">
                <label className="block text-sm font-medium text-slate-400 mb-2">シード番号 (1-64)</label>
                <select
                  value={seed}
                  onChange={(e) => setSeed(parseInt(e.target.value))}
                  className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all appearance-none"
                >
                  {seeds.map(s => (
                    <option key={s} value={s}>シード {s}</option>
                  ))}
                </select>
              </div>

              {isLoadingRegisteredDecks ? (
                <p className="py-4 text-center text-sm text-slate-500">編成を読み込んでいます...</p>
              ) : registeredDecks.length > 0 && deckScreen === "view" ? (
                <DeckRegistrationViewer
                  playerName={`Player ${seed}`}
                  playerDetail={`シード ${seed} / 編成登録完了`}
                  playerIconUrl={formPlayerIcon || null}
                  teams={selectedTeams}
                  characters={characters}
                  canEdit={canEdit}
                  onEditPlayer={canEdit ? editFull64PlayerInfo : undefined}
                  onEditTeams={canEdit ? () => setDeckScreen("edit") : undefined}
                />
              ) : (
                <div className="space-y-6" data-registration-mode="edit">
                  <PlayerIconEditor key={`full64-icon-${tournamentId}-${seed}`} iconUrl={formPlayerIcon||null} disabled={!canEdit} busy={isUploadingIcon} onUpload={uploadFull64PlayerIcon} />
                  <DeckRegistrationEditor
                    key={`full64-${tournamentId}-${seed}`}
                    teams={selectedTeams}
                    characters={characters}
                    saved={registeredDecks.length>0}
                    disabled={!canEdit}
                    dirty={deckDirty}
                    busy={isUploading?"analysis":""}
                    onTeamsChange={next=>{setSelectedTeams(next);setDeckDirty(true);}}
                    onAnalyze={analyzeFull64Teams}
                    onSave={handleSave}
                    onClose={()=>{
                      setSelectedTeams(normalizeSavedRegistrationTeams({decks:registeredDecks}));
                      setDeckDirty(false);
                      if (registeredDecks.length > 0) setDeckScreen("view");
                    }}
                  />
                </div>
              )}
            </div>
          ) : <><div className="mb-5 grid grid-cols-2 gap-4"><label className="text-xs font-bold text-slate-400">攻撃側（左）<select value={attackerSeed} onChange={event=>{if(full64MatchDirty&&!window.confirm("未保存の勝敗入力を破棄して対戦Playerを変更しますか？"))return;setFull64MatchDirty(false);setAttackerSeed(Number(event.target.value));}} className="mt-1 w-full rounded-xl bg-slate-800 p-3">{seeds.map(value=><option key={value} value={value}>シード {value}</option>)}</select></label><label className="text-right text-xs font-bold text-slate-400">防衛側（右）<select value={defenderSeed} onChange={event=>{if(full64MatchDirty&&!window.confirm("未保存の勝敗入力を破棄して対戦Playerを変更しますか？"))return;setFull64MatchDirty(false);setDefenderSeed(Number(event.target.value));}} className="mt-1 w-full rounded-xl bg-slate-800 p-3 text-left">{seeds.map(value=><option key={value} value={value}>シード {value}</option>)}</select></label></div><MatchResultEditor
            key={`full64-match-${attackerSeed}-${defenderSeed}-${matchStage}`}
            attacker={{id:attackerSeed,name:`Player ${attackerSeed}`,detail:`シード ${attackerSeed}`,iconUrl:getPlayerIconUrl(getPlayerBySeed(attackerSeed))}}
            defender={{id:defenderSeed,name:`Player ${defenderSeed}`,detail:`シード ${defenderSeed}`,iconUrl:getPlayerIconUrl(getPlayerBySeed(defenderSeed))}}
            attackerTeams={full64MatchTeams.attacker}
            defenderTeams={full64MatchTeams.defender}
            characters={characters}
            disabled={!canEdit}
            busy={isUploading}
            onAnalyze={analyzeFull64Match}
            onSave={saveFull64Match}
            onDirtyChange={setFull64MatchDirty}
          /></>}
        </div>
      </div>

    </main>
  );
}
