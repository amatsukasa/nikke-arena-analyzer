"use client";
import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Trophy, ShieldAlert, User as UserIcon, ChevronLeft, Share2 } from "lucide-react";

export default function PlayerStatsPage() {
  const params = useParams();
  const id = params.id as string;
  const seed = parseInt(params.seed as string);

  const [loading, setLoading] = useState(true);
  const [tournament, setTournament] = useState<any>(null);
  const [playerDetails, setPlayerDetails] = useState<any>(null);
  const [bracketData, setBracketData] = useState<any>(null);
  const [allCharacters, setAllCharacters] = useState<any[]>([]);

  const [tournamentId, setTournamentId] = useState<number | null>(null);

  useEffect(() => {
    const initTournament = async () => {
      try {
        const res = await fetch(`/api/championships/${id}/matches`);
        const matches = await res.json();
        
        if (matches && matches.length > 0) {
          setTournamentId(matches[0].id);
        } else {
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
        console.error("Tournament initialization failed in player stats page:", err);
      }
    };
    initTournament();
  }, [id]);

  useEffect(() => {
    if (!tournamentId) return;

    const fetchData = async () => {
      try {
        const timestamp = Date.now();
        const [tournRes, detailsRes, bracketRes, charsRes] = await Promise.all([
          fetch(`/api/tournaments/${tournamentId}?t=${timestamp}`),
          fetch(`/api/tournaments/${tournamentId}/players/${seed}/details?t=${timestamp}`),
          fetch(`/api/tournaments/${tournamentId}/bracket?t=${timestamp}`),
          fetch(`/api/characters?t=${timestamp}`)
        ]);
        
        setTournament(await tournRes.json());
        setPlayerDetails(await detailsRes.json());
        setBracketData(await bracketRes.json());
        setAllCharacters(await charsRes.json());
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [tournamentId, seed]);

  if (loading) return (
    <div className="flex h-screen items-center justify-center bg-slate-950">
      <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );

  if (!playerDetails || !playerDetails.player) {
    return (
      <div className="min-h-screen bg-slate-950 p-6 flex flex-col items-center justify-center">
        <UserIcon size={64} className="text-slate-700 mb-4" />
        <h1 className="text-2xl font-bold text-slate-300">データが見つかりません</h1>
        <p className="text-slate-500 mt-2">指定されたシード({seed})のプレイヤー情報は登録されていません。</p>
        <Link href="/" className="mt-8 px-6 py-2 bg-blue-600 hover:bg-blue-500 rounded-full font-bold text-white transition-colors">
          ダッシュボードへ戻る
        </Link>
      </div>
    );
  }

  const myPlayer = playerDetails.player;
  const myDecks = playerDetails.decks || [];

  let myTournamentResult = "グループ1回戦出場 (Best 64)";
  if (bracketData && bracketData.groups) {
     bracketData.groups.forEach((g: any) => {
        const found = g.players.find((p:any) => (p.original_seed || p.seed) === seed && p.id !== null);
        if (found) {
           const reached_qf = g.qf_winners?.includes(myPlayer.id);
           const reached_sf = g.sf_winners?.includes(myPlayer.id);
           const reached_f = g.winner === myPlayer.id;
           
           if (reached_f) myTournamentResult = "グループ優勝 (Best 8 進出)";
           else if (reached_sf) myTournamentResult = "グループ決勝進出 (Best 16)";
           else if (reached_qf) myTournamentResult = "グループ準決勝進出 (Best 32)";
           else myTournamentResult = "グループ1回戦出場 (Best 64)";
        }
     });
     
     if (bracketData.champion_finals) {
        const cf = bracketData.champion_finals;
        if (cf.players.find((p:any) => p.id === myPlayer.id)) {
           const reached_cf_sf = cf.qf_winners?.includes(myPlayer.id);
           const reached_cf_f = cf.sf_winners?.includes(myPlayer.id);
           const is_champ = cf.winner === myPlayer.id;

           if (is_champ) myTournamentResult = "🏆 チャンピオン 🏆";
           else if (reached_cf_f) myTournamentResult = "準優勝 (2位)";
           else if (reached_cf_sf) myTournamentResult = "ベスト4";
           else myTournamentResult = "チャンピオン対抗戦出場 (Best 8)";
        }
     }
  }

  const TeamDisplay = ({ charIds }: { charIds: number[] }) => {
    const displayChars = charIds.map(cid => allCharacters.find(c => c.id === cid)).filter(Boolean);
    return (
      <div className="flex space-x-2">
        {displayChars.map((c: any, i: number) => {
          if (c.id === 9999) return <div key={i} className="w-12 h-12 rounded-lg bg-slate-800 ring-1 ring-white/10" />;
          return (
            <div key={i} className="w-12 h-12 rounded-lg bg-slate-800 ring-1 ring-white/20 overflow-hidden relative group">
              {c.is_template_available ? (
                <img src={`/api/char-icon/${c.id}.png?t=${Date.now()}`} alt={c.name} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-slate-700">
                  <span className="text-[10px] font-bold text-slate-300">{c.name?.slice(0,3)}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({
        title: `${myPlayer.name} の成績 - NIKKE Arena Analyzer`,
        url: window.location.href
      });
    } else {
      alert("共有機能がサポートされていません");
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 pb-24 font-sans text-slate-200">
      <div className="max-w-4xl mx-auto p-4 md:p-8">
        
        {/* Navigation */}
        <div className="flex items-center justify-between mb-8">
          <Link href="/" className="flex items-center space-x-2 text-slate-400 hover:text-white transition-colors">
            <ChevronLeft size={20} />
            <span className="font-bold text-sm">ダッシュボードへ戻る</span>
          </Link>
          <button onClick={handleShare} className="flex items-center space-x-2 px-4 py-2 bg-blue-600/20 text-blue-400 hover:bg-blue-600 hover:text-white rounded-full font-bold transition-all ring-1 ring-blue-500/50">
            <Share2 size={16} />
            <span className="text-sm">結果をシェア</span>
          </button>
        </div>

        {/* Screenshot Target Area */}
        <div className="bg-slate-900/80 backdrop-blur-xl rounded-[2.5rem] ring-1 ring-white/10 shadow-[0_0_50px_rgba(0,0,0,0.5)] overflow-hidden">
          
          {/* Header Section */}
          <div className="relative p-8 md:p-12 overflow-hidden bg-gradient-to-br from-slate-800 to-slate-900">
            <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none transform translate-x-10 -translate-y-10">
               <Trophy size={250} />
            </div>
            <div className="absolute inset-0 bg-gradient-to-r from-blue-500/10 to-emerald-500/10 pointer-events-none"></div>

            <div className="relative flex flex-col md:flex-row items-center space-y-6 md:space-y-0 md:space-x-8 z-10">
              <div className="w-32 h-32 md:w-40 md:h-40 rounded-full border-4 border-amber-500 shadow-[0_0_40px_rgba(245,158,11,0.4)] bg-slate-950 overflow-hidden shrink-0 flex items-center justify-center">
                  {myPlayer.icon_url ? (
                     <img src={myPlayer.icon_url} alt="Player Icon" className="w-full h-full object-cover" />
                  ) : (
                     <UserIcon size={80} className="text-slate-600" />
                  )}
              </div>
              <div className="text-center md:text-left">
                 <p className="text-amber-400 font-bold mb-1 text-sm md:text-base tracking-widest uppercase">Personal Stats</p>
                 <h1 className="text-4xl md:text-5xl font-black text-white mb-4 drop-shadow-lg">{myPlayer.name}</h1>
                 <div className="inline-block bg-gradient-to-r from-amber-500 to-orange-600 text-white px-6 py-2 rounded-full font-black text-lg md:text-xl shadow-[0_4px_15px_rgba(245,158,11,0.5)] border border-amber-400/50">
                    {myTournamentResult}
                 </div>
                 <div className="mt-4 text-slate-400 text-sm font-medium">
                   {tournament?.name} (シード {seed})
                 </div>
              </div>
            </div>
          </div>

          {/* Stats & Decks Section */}
          <div className="p-8 md:p-12">
            <h2 className="text-2xl font-black text-slate-100 mb-8 flex items-center space-x-3">
               <ShieldAlert className="text-blue-400" size={28} />
               <span>登録編成と戦績</span>
            </h2>

            <div className="space-y-6">
               {myDecks.map((deck: any) => {
                 const isHighWinrate = deck.win_rate >= 50;
                 return (
                  <div key={deck.team_number} className="relative overflow-hidden bg-slate-800/50 p-6 rounded-3xl ring-1 ring-white/5 shadow-xl hover:ring-white/10 transition-all">
                    {isHighWinrate && (
                      <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/10 blur-3xl rounded-full"></div>
                    )}
                    
                    <div className="flex flex-col md:flex-row items-center justify-between relative z-10">
                      <div className="flex items-center space-x-6 mb-6 md:mb-0">
                         <div className="flex flex-col items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-slate-700 to-slate-900 ring-1 ring-white/10 shadow-inner shrink-0">
                            <span className="text-[10px] text-slate-400 font-bold tracking-wider">TEAM</span>
                            <span className="text-2xl font-black text-white">{deck.team_number}</span>
                         </div>
                         <TeamDisplay charIds={deck.character_ids} />
                      </div>
                      
                      <div className="flex items-center space-x-6 bg-slate-900/80 px-6 py-4 rounded-2xl ring-1 ring-white/5 backdrop-blur-md">
                         <div className="flex flex-col text-right">
                            <span className="text-xs text-slate-500 font-bold uppercase tracking-wider">Win Rate</span>
                            <span className={`text-3xl font-black ${isHighWinrate ? 'text-emerald-400 drop-shadow-[0_0_10px_rgba(52,211,153,0.5)]' : 'text-amber-400'}`}>
                               {deck.win_rate}%
                            </span>
                         </div>
                         <div className="h-12 w-px bg-white/10"></div>
                         <div className="flex flex-col text-left space-y-1">
                            <span className="text-sm font-bold text-emerald-400 flex items-center justify-between w-16">
                              <span>W:</span><span>{deck.wins}</span>
                            </span>
                            <span className="text-sm font-bold text-slate-500 flex items-center justify-between w-16">
                              <span>L:</span><span>{deck.losses}</span>
                            </span>
                         </div>
                      </div>
                    </div>
                  </div>
                 );
               })}
            </div>
            
            {myDecks.length === 0 && (
              <div className="text-center py-12 text-slate-500 font-bold bg-slate-800/30 rounded-3xl border border-dashed border-slate-700">
                編成データが登録されていません
              </div>
            )}
          </div>
          
        </div>
        
      </div>
    </div>
  );
}
