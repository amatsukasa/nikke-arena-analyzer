"use client";
export const dynamic = 'force-dynamic';
import { useState, useRef, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { Upload, ChevronLeft, User, ShieldAlert, CheckCircle2, Trophy, ChevronDown, Check, Swords, Scissors, ZoomIn, X, Save, BarChart3 } from "lucide-react";
import Link from "next/link";
import Cropper from "react-easy-crop";

export default function TournamentDetail() {
  const params = useParams();
  const id = params.id;
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLDivElement>(null);

  const [seed, setSeed] = useState(1);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [result, setResult] = useState<any>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [characters, setCharacters] = useState<any[]>([]);
  const [selectedTeams, setSelectedTeams] = useState<any[]>([]);
  const [expandedPreviewRound, setExpandedPreviewRound] = useState(0);

  // 勝敗登録用state
  const [mode, setMode] = useState<"deck" | "match">("deck");
  const [attackerSeed, setAttackerSeed] = useState(1);
  const [defenderSeed, setDefenderSeed] = useState(2);
  const [matchFile, setMatchFile] = useState<File | null>(null);
  const [matchPreview, setMatchPreview] = useState<string | null>(null);
  const [matchResult, setMatchResult] = useState<any>(null);
  const [matchStage, setMatchStage] = useState("Groups");

  // フォーム用プレイヤー情報
  const [formPlayerName, setFormPlayerName] = useState("");
  const [formPlayerIcon, setFormPlayerIcon] = useState("");

  // クロップ用ステート
  const [showCropModal, setShowCropModal] = useState(false);
  const [imageToCrop, setImageToCrop] = useState<string | null>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<any>(null);
  const [isUploadingIcon, setIsUploadingIcon] = useState(false);
  const [cropTarget, setCropTarget] = useState<"form" | "result">("form");

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

  // 1. Championship ID から紐づく Tournament ID を取得する。無ければ自動作成する。
  useEffect(() => {
    const initTournament = async () => {
      try {
        // 大会に紐づく対戦/トーナメント一覧を取得
        const res = await fetch(`/api/championships/${id}/matches`);
        const matches = await res.json();
        
        if (matches && matches.length > 0) {
          // すでに作成済みのトーナメントがある場合、それを選択
          setTournamentId(matches[0].id);
        } else {
          // 無ければ新しく作成する
          const champRes = await fetch(`/api/championships/${id}`);
          const champ = await champRes.json();
          
          const createRes = await fetch(`/api/tournaments`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: champ.name || `Championship ${id} Tournament`,
              date: champ.date || new Date().toISOString().split('T')[0],
              championship_id: parseInt(id as string)
            })
          });
          const newTourn = await createRes.json();
          setTournamentId(newTourn.id);
        }
      } catch (err) {
        console.error("Tournament initialization failed:", err);
      }
    };
    initTournament();
  }, [id]);

  useEffect(() => {
    fetch("/api/characters").then(r => r.json()).then(setCharacters);
  }, []);

  useEffect(() => {
    if (tournamentId) {
      fetchBracket();
    }
  }, [tournamentId]);

  // シード番号変更時に既存のプレイヤー情報を取得
  useEffect(() => {
    if (mode === "deck" && tournamentId) {
      fetch(`/api/tournaments/${tournamentId}/players/${seed}/details`)
        .then(r => r.json())
        .then(data => {
          if (data.player) {
            setFormPlayerName(data.player.name);
            setFormPlayerIcon(data.player.icon_url || "");
          } else {
            setFormPlayerName(`Player ${seed}`);
            setFormPlayerIcon("");
          }
        });
    }
  }, [seed, mode, tournamentId]);

  const seeds = Array.from({ length: 64 }, (_, i) => i + 1);
  const resultsRef = useRef<HTMLDivElement>(null);

  const handlePlayerClick = (s: number) => {
    setMode("deck");
    setSeed(s);
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handlePairClick = (s1: number, s2: number, stage: string) => {
    setMode("match");
    setAttackerSeed(s1);
    setDefenderSeed(s2);
    setMatchStage(stage);
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // --- クロップ関連のヘルパー ---
  const onCropComplete = (croppedArea: any, croppedAreaPixels: any) => {
    setCroppedAreaPixels(croppedAreaPixels);
  };

  const handleIconUpload = async () => {
    if (!imageToCrop || !croppedAreaPixels) return;
    setIsUploadingIcon(true);
    try {
      const croppedImage = await getCroppedImg(imageToCrop, croppedAreaPixels);
      const formData = new FormData();
      formData.append("image", croppedImage, "avatar.png");

      const res = await fetch("/api/upload/player-icon", { method: "POST", body: formData });
      const data = await res.json();

      const bustUrl = `${data.url}?t=${Date.now()}`;

      // 常に基本フォーム側のアイコンを更新
      setFormPlayerIcon(bustUrl);

      // 解析結果が表示されている場合は、そちらの表示も更新
      if (result) {
        setResult((prev: any) => ({ ...prev, player_icon_url: bustUrl }));
      }

      setShowCropModal(false);
      setImageToCrop(null);
    } catch (e) {
      console.error(e);
    } finally {
      setIsUploadingIcon(false);
    }
  };

  const onFileChange = async (e: any) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.addEventListener("load", () => {
        setImageToCrop(reader.result as string);
        setShowCropModal(true);
      });
      reader.readAsDataURL(file);
    }
  };

  async function getCroppedImg(imageSrc: string, pixelCrop: any): Promise<Blob> {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.addEventListener("load", () => resolve(img));
      img.addEventListener("error", (error) => reject(error));
      img.src = imageSrc;
    });

    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas context is null");

    canvas.width = pixelCrop.width;
    canvas.height = pixelCrop.height;

    ctx.drawImage(
      image,
      pixelCrop.x,
      pixelCrop.y,
      pixelCrop.width,
      pixelCrop.height,
      0,
      0,
      pixelCrop.width,
      pixelCrop.height
    );

    return new Promise((resolve) => {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
      }, "image/png");
    });
  }

  // ------------------
  // Upload Handlers
  // ------------------
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setFiles(prev => {
        const combined = [...prev, ...newFiles].slice(0, 5);
        setPreviews(combined.map(f => URL.createObjectURL(f)));
        return combined;
      });
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    setFiles([]);
    setPreviews([]);
  };

  const handleUpload = async () => {
    if (files.length === 0 || !tournamentId) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append("tournament_id", tournamentId.toString());
    formData.append("seed_number", seed.toString());
    files.forEach(f => formData.append("images", f));

    try {
      const res = await fetch("/api/analyze/deck", { method: "POST", body: formData });
      const data = await res.json();

      // フォームの入力を解析結果に統合
      const augmentedData = {
        ...data,
        suggested_player_name: formPlayerName || data.suggested_player_name,
        player_icon_url: formPlayerIcon || data.player_icon_url
      };

      setResult(augmentedData);
      setExpandedPreviewRound(0);
      setSelectedTeams(augmentedData.suggested_teams.map((team: any, r_idx: number) => ({
        team_number: r_idx + 1,
        characters: team.map((c: any) => ({
          id: c.predicted_character_id || "",
          image_url: c.image_url,
          original_predicted_id: c.predicted_character_id ?? null,
          was_unrecognized: c.predicted_character_id == null,
          add_to_templates: false
        }))
      })));
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    } catch (err) {
      alert("エラーが発生しました。");
    } finally {
      setIsUploading(false);
    }
  };

  const movePreviewRound = (roundIndex: number, offset: number) => {
    const targetIndex = roundIndex + offset;
    if (targetIndex < 0 || targetIndex >= result.suggested_teams.length) return;

    const suggestedTeams = [...result.suggested_teams];
    [suggestedTeams[roundIndex], suggestedTeams[targetIndex]] = [
      suggestedTeams[targetIndex],
      suggestedTeams[roundIndex]
    ];
    setResult((prev: any) => ({ ...prev, suggested_teams: suggestedTeams }));

    const teams = [...selectedTeams];
    [teams[roundIndex], teams[targetIndex]] = [teams[targetIndex], teams[roundIndex]];
    setSelectedTeams(teams.map((team, index) => ({ ...team, team_number: index + 1 })));
    setExpandedPreviewRound(targetIndex);
  };

  const updateSelectedCharacter = (roundIndex: number, characterIndex: number, characterId: number | null) => {
    setSelectedTeams(prev => prev.map((team, teamIndex) => (
      teamIndex !== roundIndex
        ? team
        : {
            ...team,
            characters: team.characters.map((character: any, index: number) => (
              index === characterIndex
                ? {
                    ...character,
                    id: characterId,
                    add_to_templates: character.was_unrecognized
                      && characterId !== null
                      && characterId !== 9999
                  }
                : character
            ))
          }
    )));
  };

  const handleSave = async () => {
    const unresolvedSlots = selectedTeams.flatMap((team, roundIndex) =>
      team.characters.flatMap((character: any, characterIndex: number) =>
        character.id
          ? []
          : [`R${roundIndex + 1}・${characterIndex + 1}人目`]
      )
    );
    if (unresolvedSlots.length > 0) {
      alert(
        "不明のキャラクターが残っているため登録できません。\n"
        + "キャラクター名または「空枠」を選択してください。\n\n"
        + unresolvedSlots.map(slot => `・${slot}`).join("\n")
      );
      return;
    }

    // 重複チェック (ID: 9999 は空枠なので除外)
    const allIds: number[] = [];
    const duplicates: Set<number> = new Set();
    selectedTeams.forEach(team => {
      team.characters.forEach((c: any) => {
        if (c.id && c.id !== 9999) {
          if (allIds.includes(c.id)) {
            duplicates.add(c.id);
          }
          allIds.push(c.id);
        }
      });
    });

    if (duplicates.size > 0) {
      const dupNames = Array.from(duplicates).map(id => characters.find(c => c.id === id)?.name || id).join("、");
      alert(`同じキャラクターを複数の部隊に編成することはできません。\n重複しているキャラクター: ${dupNames}`);
      return;
    }

    const getCharacterName = (characterId: number | null) => {
      if (characterId == null) return "（不明）";
      if (characterId === 9999) return "空枠";
      return characters.find(c => c.id === characterId)?.name || `ID:${characterId}`;
    };
    const correctedCharacters = selectedTeams.flatMap((team, roundIndex) =>
      team.characters.flatMap((character: any, characterIndex: number) => {
        if (!character.add_to_templates) return [];
        const characterName = getCharacterName(character.id);
        return [`R${roundIndex + 1}・${characterIndex + 1}人目：（不明）→ ${characterName}`];
      })
    );
    const changedPredictions = selectedTeams.flatMap((team, roundIndex) =>
      team.characters.flatMap((character: any, characterIndex: number) => {
        const originalId = character.original_predicted_id;
        if (
          character.was_unrecognized
          || originalId === 9999
          || character.id === originalId
        ) {
          return [];
        }
        return [
          `R${roundIndex + 1}・${characterIndex + 1}人目：`
          + `${getCharacterName(originalId)} → ${getCharacterName(character.id)}`
        ];
      })
    );
    const correctionSummary = correctedCharacters.length > 0
      ? correctedCharacters.map(line => `・${line}`).join("\n")
      : "・なし";
    const predictionChangeSummary = changedPredictions.length > 0
      ? changedPredictions.map(line => `・${line}`).join("\n")
      : "・なし";
    const emptySlots = selectedTeams.flatMap((team, roundIndex) =>
      team.characters.flatMap((character: any, characterIndex: number) =>
        character.id === 9999
          ? [`R${roundIndex + 1}・${characterIndex + 1}人目`]
          : []
      )
    );
    const emptySlotSummary = emptySlots.length > 0
      ? emptySlots.map(slot => `・${slot}`).join("\n")
      : "・なし";
    const templateNotice = correctedCharacters.length > 0
      ? "\n\n補正した画像は、今後の解析テンプレートへ自動追加されます。"
      : "";
    const playerLabel = result?.suggested_player_name || `Player ${seed}`;

    if (!window.confirm(
      `${playerLabel}（シード${seed}）をこの内容で登録しますか？\n\n`
      + `不明から補正したキャラ：\n${correctionSummary}`
      + `\n\n推測結果から変更したキャラ：\n${predictionChangeSummary}`
      + `\n\n空枠：\n${emptySlotSummary}`
      + templateNotice
    )) {
      return;
    }

    if (!tournamentId) return;
    try {
      const res = await fetch(`/api/tournaments/${tournamentId}/teams`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          seed_number: seed,
          teams: selectedTeams,
          player_name: result?.suggested_player_name,
          player_icon_url: result?.player_icon_url
        })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.is_update) {
          alert("既存の編成データを上書きしました！（古いデータは自動削除済み）");
        } else {
          alert("編成データを保存しました！");
        }
        setSeed(prev => prev < 64 ? prev + 1 : 1);
        setFiles([]);
        setPreviews([]);
        setResult(null);
        fetchBracket();
      } else {
        alert("保存に失敗しました。");
      }
    } catch (err) {
      alert("エラーが発生しました。");
    }
  };

  const handleSavePlayerInfo = async () => {
    if (!tournamentId) return;
    try {
      const res = await fetch(`/api/tournaments/${tournamentId}/players/${seed}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formPlayerName,
          icon_url: formPlayerIcon
        })
      });
      if (res.ok) {
        alert("プレイヤー情報を保存しました！");
        // 解析結果（result）のステートも同期させる
        if (result) {
          setResult((prev: any) => ({
            ...prev,
            suggested_player_name: formPlayerName,
            player_icon_url: formPlayerIcon
          }));
        }
        fetchBracket();
      } else {
        alert("保存に失敗しました。");
      }
    } catch (err) {
      alert("エラーが発生しました。");
    }
  };

  const handleMatchFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      setMatchFile(file);
      setMatchPreview(URL.createObjectURL(file));
    }
  };

  const handleMatchUpload = async () => {
    if (!matchFile || !tournamentId) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append("tournament_id", tournamentId.toString());
    formData.append("attacker_seed", attackerSeed.toString());
    formData.append("defender_seed", defenderSeed.toString());
    formData.append("stage", matchStage);
    formData.append("image", matchFile);

    try {
      const res = await fetch("/api/analyze/match_result", { method: "POST", body: formData });
      const data = await res.json();
      setMatchResult(data);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    } catch (err) {
      alert("解析エラーが発生しました。");
    } finally {
      setIsUploading(false);
    }
  };

  const handleMatchSave = async () => {
    if (!tournamentId) return;
    try {
      const res = await fetch(`/api/tournaments/${tournamentId}/matches`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(matchResult)
      });
      if (res.ok) {
        alert("勝敗データを保存しました！");
        setMatchFile(null);
        setMatchPreview(null);
        setMatchResult(null);
        fetchBracket();
        // トーナメント表に自動スクロール
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        alert("保存に失敗しました。両プレイヤーの編成が登録されている必要があります。");
      }
    } catch (err) {
      alert("エラーが発生しました。");
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

    return (
      <div
        onClick={(e) => {
          e.stopPropagation();
          if (!isUnknown) handlePlayerClick(player.original_seed || player.seed);
        }}
        className={`flex items-center gap-2 p-1.5 rounded-full border transition-all bg-slate-900/90 backdrop-blur-md ${isUnknown ? 'cursor-default' : 'cursor-pointer hover:bg-slate-800'} ${isWinner ? 'border-amber-400 shadow-[0_0_15px_rgba(251,191,36,0.4)] z-30 relative' : 'border-slate-600/50 hover:border-blue-400'} ${align === 'right' ? 'flex-row-reverse' : ''}`}
        style={{ transform: `scale(${scale})` }}
      >
        <div className={`relative w-10 h-10 rounded-full shrink-0 border-2 bg-slate-800 overflow-hidden flex items-center justify-center ${isWinner ? 'border-amber-400' : 'border-slate-700'}`}>
          {iconUrl ? (
            <img src={iconUrl} alt="icon" className="w-full h-full object-cover" />
          ) : (
            <User size={20} className="text-slate-600" />
          )}
        </div>
        <div className={`flex flex-col justify-center px-2 min-w-[80px] max-w-[100px] ${align === 'right' ? 'items-end text-right' : 'items-start text-left'}`}>
          <div className="text-[10px] text-slate-400 font-bold tracking-wider">SEED {player.seed}</div>
          <div className={`text-xs font-black truncate w-full ${isWinner ? 'text-amber-400' : 'text-slate-200'}`}>{player.name}</div>
        </div>
      </div>
    );
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
        <Link
          href={`/tournament/${id}/dashboard`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex min-h-11 items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-blue-500"
        >
          <BarChart3 size={18} />
          <span>大会分析を表示</span>
        </Link>
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
            onClick={() => setMode("deck")}
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
              <div>
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

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">プレイヤー名</label>
                  <input
                    type="text"
                    value={formPlayerName}
                    onChange={(e) => setFormPlayerName(e.target.value)}
                    className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                    placeholder="プレイヤー名を入力"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">顔画像 (オプション)</label>
                  <div className="flex items-center space-x-4">
                    <div className="w-20 h-20 rounded-full border-2 border-emerald-500 bg-slate-800 overflow-hidden shrink-0 flex items-center justify-center shadow-[0_0_15px_rgba(16,185,129,0.3)]">
                      {formPlayerIcon ? (
                        <img src={formPlayerIcon} alt="Preview" className="w-full h-full object-cover" />
                      ) : (
                        <User size={32} className="text-slate-600" />
                      )}
                    </div>
                    <button
                      onClick={() => {
                        setCropTarget("form");
                        const input = document.createElement("input");
                        input.type = "file";
                        input.accept = "image/*";
                        input.onchange = onFileChange;
                        input.click();
                      }}
                      className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-bold border border-white/5 transition-all"
                    >
                      画像を編集
                    </button>
                  </div>
                </div>

                <div className="pt-2">
                  <button
                    onClick={handleSavePlayerInfo}
                    className="w-full py-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 rounded-xl text-xs font-bold border border-emerald-500/30 transition-all flex items-center justify-center space-x-2"
                  >
                    <Save size={14} />
                    <span>プレイヤー情報（名前・画像）のみを保存</span>
                  </button>
                </div>
              </div>

              <div>
                <div className="flex justify-between items-end mb-2">
                  <label className="block text-sm font-medium text-slate-400">スクリーンショット ({files.length} / 5枚)</label>
                  {files.length > 0 && (
                    <button onClick={handleClear} className="px-3 py-1 bg-red-500/20 text-red-400 rounded-lg text-sm font-bold hover:bg-red-500/30 transition-colors">
                      すべてクリア
                    </button>
                  )}
                </div>

                <div className="bg-slate-800/50 border border-white/10 rounded-xl p-4">
                  {previews.length > 0 && (
                    <div className="grid grid-cols-5 gap-2 mb-4">
                      {previews.map((p, idx) => (
                        <div key={idx} className="relative aspect-[9/16]">
                          <img src={p} alt={`Preview ${idx}`} className="w-full h-full object-cover rounded-lg shadow-lg border border-white/10" />
                          <div className="absolute top-0 right-0 bg-black/60 text-white text-[10px] px-1 rounded-bl-lg rounded-tr-lg">{idx + 1}</div>
                        </div>
                      ))}
                      {Array.from({ length: 5 - previews.length }).map((_, idx) => (
                        <div key={`empty-${idx}`} className="aspect-[9/16] rounded-lg border border-dashed border-white/20 flex flex-col items-center justify-center text-white/20">
                          <Upload size={16} className="mb-1 opacity-50" />
                          <span className="text-[10px]">空き</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {files.length < 5 && (
                    <button onClick={() => fileInputRef.current?.click()} className="w-full py-4 border-2 border-dashed border-blue-500/50 bg-blue-500/10 hover:bg-blue-500/20 rounded-xl flex flex-col items-center justify-center transition-colors text-blue-400">
                      <Upload size={24} className="mb-2" />
                      <span className="font-bold">画像を追加する</span>
                    </button>
                  )}
                  <input type="file" ref={fileInputRef} onChange={handleFileChange} multiple accept="image/*" className="hidden" />
                </div>
              </div>

              <button
                onClick={handleUpload}
                disabled={files.length !== 5 || isUploading}
                className={`w-full py-4 rounded-xl font-bold transition-all shadow-lg text-lg flex items-center justify-center space-x-2
                ${files.length === 5 && !isUploading ? "bg-blue-500 hover:bg-blue-600 text-white shadow-blue-500/25" : "bg-slate-800 text-slate-500 cursor-not-allowed"}`}
              >
                {isUploading ? <span>AIが解析中...</span> : <span>AIで編成を解析する</span>}
              </button>
            </div>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">攻撃側 (左)</label>
                  <div className="flex items-center space-x-2">
                    <div className="w-10 h-10 rounded-full border border-slate-600 bg-slate-800 overflow-hidden shrink-0 flex items-center justify-center">
                      {getPlayerIconUrl(getPlayerBySeed(attackerSeed)) ? (
                        <img src={getPlayerIconUrl(getPlayerBySeed(attackerSeed))} className="w-full h-full object-cover" />
                      ) : (
                        <User size={16} className="text-slate-500" />
                      )}
                    </div>
                    <select value={attackerSeed} onChange={(e) => setAttackerSeed(parseInt(e.target.value))} className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-3 py-2 text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500">
                      {seeds.map(s => <option key={s} value={s}>シード {s}</option>)}
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1 text-right">防衛側 (右)</label>
                  <div className="flex items-center space-x-2 flex-row-reverse">
                    <div className="w-10 h-10 rounded-full border border-slate-600 bg-slate-800 overflow-hidden shrink-0 flex items-center justify-center ml-2">
                      {getPlayerIconUrl(getPlayerBySeed(defenderSeed)) ? (
                        <img src={getPlayerIconUrl(getPlayerBySeed(defenderSeed))} className="w-full h-full object-cover" />
                      ) : (
                        <User size={16} className="text-slate-500" />
                      )}
                    </div>
                    <select value={defenderSeed} onChange={(e) => setDefenderSeed(parseInt(e.target.value))} className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-3 py-2 text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500">
                      {seeds.map(s => <option key={s} value={s}>シード {s}</option>)}
                    </select>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">リザルト画面 (1枚)</label>
                <div className="bg-slate-800/50 border border-white/10 rounded-xl p-4">
                  {matchPreview ? (
                    <div className="relative aspect-[9/16] max-w-[200px] mx-auto">
                      <img src={matchPreview} className="w-full h-full object-cover rounded-lg shadow-lg border border-white/10" />
                      <button onClick={() => { setMatchFile(null); setMatchPreview(null); }} className="absolute -top-3 -right-3 bg-red-500 text-white w-8 h-8 rounded-full font-bold shadow-lg flex items-center justify-center">×</button>
                    </div>
                  ) : (
                    <label className="w-full py-12 border-2 border-dashed border-emerald-500/50 bg-emerald-500/10 hover:bg-emerald-500/20 rounded-xl flex flex-col items-center justify-center transition-colors text-emerald-400 cursor-pointer">
                      <Upload size={24} className="mb-2" />
                      <span className="font-bold">画像を選択</span>
                      <input type="file" onChange={handleMatchFileChange} accept="image/*" className="hidden" />
                    </label>
                  )}
                </div>
              </div>

              <button
                onClick={handleMatchUpload}
                disabled={!matchFile || isUploading}
                className={`w-full py-4 rounded-xl font-bold transition-all shadow-lg text-lg flex items-center justify-center space-x-2 mt-auto
                ${matchFile && !isUploading ? "bg-emerald-500 hover:bg-emerald-600 text-white shadow-emerald-500/25" : "bg-slate-800 text-slate-500 cursor-not-allowed"}`}
              >
                {isUploading ? <span>AIが解析中...</span> : <span>AIで勝敗を解析する</span>}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Results Area */}
      <div ref={resultsRef} className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-6 rounded-3xl shadow-2xl relative overflow-hidden mt-12 scroll-mt-24">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-emerald-400 to-blue-500 opacity-50"></div>
        <h2 className="text-xl font-bold mb-6 flex items-center space-x-2">
          <CheckCircle2 className="text-emerald-400" />
          <span>解析結果（プレビュー）</span>
        </h2>

        {mode === "deck" && result ? (
          <div className="space-y-6">
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl space-y-4">
              <div className="flex items-center space-x-4">
                <div className="relative group shrink-0">
                  <div className="w-16 h-16 rounded-full border-2 border-emerald-500/50 bg-slate-800 overflow-hidden shadow-lg">
                    {result.player_icon_url ? (
                      <img src={result.player_icon_url} alt="Icon" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-slate-500 bg-slate-900">
                        <User size={32} />
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => {
                      setCropTarget("result");
                      const input = document.createElement("input");
                      input.type = "file";
                      input.accept = "image/*";
                      input.onchange = onFileChange;
                      input.click();
                    }}
                    className="absolute inset-0 bg-black/40 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 rounded-full transition-all text-[10px] font-bold"
                  >
                    変更
                  </button>
                </div>
                <div className="flex-1 space-y-2">
                  <label className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider">プレイヤー名</label>
                  <input
                    type="text"
                    value={result.suggested_player_name || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setResult((prev: any) => ({ ...prev, suggested_player_name: val }));
                      setFormPlayerName(val); // フォーム側も同期
                    }}
                    className="w-full bg-slate-950/50 border border-emerald-500/30 rounded-lg px-3 py-2 text-slate-100 font-bold focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    placeholder="プレイヤー名を入力"
                  />
                  <p className="text-[10px] text-slate-500">シード: {result.suggested_seed}</p>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              {result.suggested_teams.map((team: any, idx: number) => (
                <div key={idx} className="rounded-lg border border-white/10 bg-slate-900/40 p-2 sm:border-0 sm:bg-transparent sm:p-0">
                  <div className="flex items-center gap-2">
                    <div className="flex flex-col items-center justify-center space-y-0.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => movePreviewRound(idx, -1)}
                        disabled={idx === 0}
                        className="p-1 text-slate-500 hover:text-emerald-400 disabled:opacity-20 transition-colors"
                        title="一つ上へ移動"
                      >
                        ▲
                      </button>
                      <div className="w-8 h-8 rounded bg-slate-800 flex items-center justify-center text-xs text-slate-500 font-mono ring-1 ring-white/5">R{idx + 1}</div>
                      <button
                        type="button"
                        onClick={() => movePreviewRound(idx, 1)}
                        disabled={idx === result.suggested_teams.length - 1}
                        className="p-1 text-slate-500 hover:text-emerald-400 disabled:opacity-20 transition-colors"
                        title="一つ下へ移動"
                      >
                        ▼
                      </button>
                    </div>

                    <button
                      type="button"
                      onClick={() => setExpandedPreviewRound(current => current === idx ? -1 : idx)}
                      className="flex min-h-12 flex-1 items-center justify-between rounded-md bg-slate-800/70 px-3 text-left sm:hidden"
                      aria-expanded={expandedPreviewRound === idx}
                    >
                      <span className="font-bold text-slate-200">ラウンド {idx + 1}</span>
                      <span className="flex items-center gap-2">
                        {(() => {
                          const missingCount = selectedTeams[idx]?.characters.filter((character: any) => !character.id).length ?? team.length;
                          return missingCount > 0
                            ? <span className="text-sm font-bold text-red-400">未確認 {missingCount}</span>
                            : <span className="text-sm font-bold text-emerald-400">確認済み</span>;
                        })()}
                        <ChevronDown className={`h-5 w-5 text-slate-400 transition-transform ${expandedPreviewRound === idx ? "rotate-180" : ""}`} />
                      </span>
                    </button>

                    <div className="hidden min-w-0 flex-1 grid-cols-5 gap-2 sm:grid">
                      {team.map((char: any, c_idx: number) => (
                        <div key={c_idx} className="flex min-w-0 flex-col items-center gap-2">
                          <div className="h-16 w-16 overflow-hidden rounded-lg bg-slate-800/50 ring-1 ring-white/5">
                            {char?.image_url ? <img src={char.image_url} alt={`R${idx + 1}-C${c_idx + 1}`} loading="lazy" decoding="async" className="h-full w-full object-cover" /> : <div className="flex h-full w-full items-center justify-center text-xs text-slate-600">-</div>}
                          </div>
                          <select
                            className={`h-10 w-full min-w-0 rounded px-2 text-sm ${!selectedTeams[idx]?.characters[c_idx]?.id ? 'bg-red-950/80 text-red-400 border-2 border-red-500 font-bold shadow-[0_0_10px_rgba(239,68,68,0.5)]' : 'bg-slate-800 border border-slate-700 text-slate-300'}`}
                            value={selectedTeams[idx]?.characters[c_idx]?.id || ""}
                            onChange={(e) => updateSelectedCharacter(idx, c_idx, e.target.value ? parseInt(e.target.value) : null)}
                            aria-label={`ラウンド${idx + 1} キャラクター${c_idx + 1}`}
                          >
                            <option value="">(不明)</option>
                            {characters.map(c =>
                              <option key={c.id} value={c.id}>
                                {c.id === 9999 ? '空枠' : `[${c.rarity}] ${c.name}`}
                              </option>
                            )}
                          </select>
                        </div>
                      ))}
                    </div>
                  </div>

                  {expandedPreviewRound === idx && (
                    <div className="mt-2 space-y-2 sm:hidden">
                      {team.map((char: any, c_idx: number) => (
                        <div key={c_idx} className="flex min-w-0 items-center gap-3 rounded-md bg-slate-950/50 p-2">
                          <div className="h-12 w-12 shrink-0 overflow-hidden rounded-md bg-slate-800/50 ring-1 ring-white/5">
                            {char?.image_url ? <img src={char.image_url} alt={`R${idx + 1}-C${c_idx + 1}`} loading="lazy" decoding="async" className="h-full w-full object-cover" /> : <div className="flex h-full w-full items-center justify-center text-xs text-slate-600">-</div>}
                          </div>
                          <div className="min-w-0 flex-1">
                            <label className="mb-1 block text-xs text-slate-500" htmlFor={`round-${idx}-character-${c_idx}`}>キャラクター {c_idx + 1}</label>
                            <select
                              id={`round-${idx}-character-${c_idx}`}
                              className={`min-h-11 w-full min-w-0 rounded px-3 text-base ${!selectedTeams[idx]?.characters[c_idx]?.id ? 'bg-red-950/80 text-red-400 border-2 border-red-500 font-bold shadow-[0_0_10px_rgba(239,68,68,0.5)]' : 'bg-slate-800 border border-slate-700 text-slate-200'}`}
                              value={selectedTeams[idx]?.characters[c_idx]?.id || ""}
                              onChange={(e) => updateSelectedCharacter(idx, c_idx, e.target.value ? parseInt(e.target.value) : null)}
                            >
                              <option value="">(不明)</option>
                              {characters.map(c =>
                                <option key={c.id} value={c.id}>
                                  {c.id === 9999 ? '空枠' : `[${c.rarity}] ${c.name}`}
                                </option>
                              )}
                            </select>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <button onClick={handleSave} className="w-full py-4 bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 rounded-xl font-bold transition-all shadow-lg">
              この内容で編成を登録
            </button>
          </div>
        ) : mode === "match" && matchResult ? (
          <div className="space-y-6">
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl">
              <div className="flex items-center justify-between font-bold mb-4">
                <div className="text-blue-400 text-lg">シード {matchResult.attacker_seed} (左)</div>
                <div className="text-slate-400 text-sm">VS</div>
                <div className="text-red-400 text-lg">シード {matchResult.defender_seed} (右)</div>
              </div>

              <div className="space-y-2">
                {matchResult.rounds.map((r: any) => (
                  <div key={r.round} className="flex items-center justify-between bg-slate-800/50 p-3 rounded-lg ring-1 ring-white/5">
                    <div className="w-8 text-slate-500 font-mono text-xs">R{r.round}</div>
                    <div className={`flex-1 text-center font-black ${r.left === 'WIN' ? 'text-blue-400' : 'text-red-400'}`}>{r.left}</div>
                    <div className="flex-1 text-center font-black flex items-center justify-center">
                      <select
                        className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300"
                        value={r.left === "WIN" ? "left" : "right"}
                        onChange={(e) => {
                          const newResult = { ...matchResult };
                          const isLeftWin = e.target.value === "left";
                          newResult.rounds[r.round - 1].left = isLeftWin ? "WIN" : "LOSE";
                          newResult.rounds[r.round - 1].right = isLeftWin ? "LOSE" : "WIN";
                          let lw = 0, rw = 0;
                          newResult.rounds.forEach((rr: any) => rr.left === "WIN" ? lw++ : rw++);
                          newResult.winner = lw > rw ? "left" : "right";
                          setMatchResult(newResult);
                        }}
                      >
                        <option value="left">左の勝利</option>
                        <option value="right">右の勝利</option>
                      </select>
                    </div>
                    <div className={`flex-1 text-center font-black ${r.right === 'WIN' ? 'text-blue-400' : 'text-red-400'}`}>{r.right}</div>
                  </div>
                ))}
              </div>

              <div className="mt-6 text-center">
                <p className="text-slate-400 text-sm mb-1">最終結果</p>
                <p className="text-2xl font-black text-emerald-400">
                  {matchResult.winner === "left" ? "左側のプレイヤーの勝利！" : "右側のプレイヤーの勝利！"}
                </p>
              </div>
            </div>

            <button onClick={handleMatchSave} className="w-full py-4 bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 rounded-xl font-bold transition-all shadow-lg">
              この内容で勝敗を登録する
            </button>
          </div>
        ) : (
          <div className="h-full min-h-[100px] flex flex-col items-center justify-center text-slate-500">
            <p>画像をアップロードすると解析結果が表示されます</p>
          </div>
        )}
      </div>
      {/* クロップモーダル */}
      {showCropModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/90 backdrop-blur-md">
          <div className="bg-slate-900 ring-1 ring-white/10 rounded-3xl w-full max-w-lg overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
            <div className="p-6 border-b border-white/5 flex items-center justify-between">
              <h3 className="text-xl font-black text-white flex items-center space-x-2">
                <Scissors className="text-blue-400" size={20} />
                <span>プロフィール画像の編集</span>
              </h3>
              <button onClick={() => setShowCropModal(false)} className="text-slate-400 hover:text-white">
                <X size={24} />
              </button>
            </div>

            <div className="relative flex-1 min-h-[400px] bg-black">
              {imageToCrop && (
                <Cropper
                  image={imageToCrop}
                  crop={crop}
                  zoom={zoom}
                  maxZoom={10}
                  aspect={1}
                  onCropChange={setCrop}
                  onCropComplete={onCropComplete}
                  onZoomChange={setZoom}
                  cropShape="round"
                  showGrid={false}
                />
              )}
            </div>

            <div className="p-6 space-y-6 bg-slate-900">
              <div className="space-y-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400 flex items-center space-x-1">
                    <ZoomIn size={14} />
                    <span>ズーム調節</span>
                  </span>
                  <span className="text-blue-400 font-bold">{Math.round(zoom * 100)}%</span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    onClick={() => setZoom(1)}
                    className={`py-2 px-3 rounded-lg text-sm font-bold transition-all ${
                      zoom === 1 ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                    }`}
                  >
                    小 (1倍)
                  </button>
                  <button
                    onClick={() => setZoom(6)}
                    className={`py-2 px-3 rounded-lg text-sm font-bold transition-all ${
                      zoom === 6 ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                    }`}
                  >
                    中 (6倍)
                  </button>
                  <button
                    onClick={() => setZoom(10)}
                    className={`py-2 px-3 rounded-lg text-sm font-bold transition-all ${
                      zoom === 10 ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                    }`}
                  >
                    大 (10倍)
                  </button>
                </div>
              </div>

              <div className="flex space-x-4">
                <button
                  onClick={() => setShowCropModal(false)}
                  className="flex-1 py-3 px-6 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold rounded-xl transition-all"
                >
                  キャンセル
                </button>
                <button
                  onClick={handleIconUpload}
                  disabled={isUploadingIcon}
                  className="flex-1 py-3 px-6 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold rounded-xl shadow-lg shadow-blue-900/20 transition-all flex items-center justify-center space-x-2"
                >
                  {isUploadingIcon ? (
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <>
                      <Check size={20} />
                      <span>決定してアップロード</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
