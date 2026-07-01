"use client";

import { useRouter } from "next/navigation";
import { ChevronLeft, Users } from "lucide-react";
import Link from "next/link";

export interface CharacterDetailViewProps {
  mode: "cross" | "single";
  characterId: number;
  tournamentId?: number;
  tournamentIds?: number[];
  stats: {
    character_usage?: any[];
    team_usage?: any[];
  } | null;
  allCharacters: any[];
  title: string;
}

export default function CharacterDetailView({
  mode,
  characterId,
  tournamentId,
  tournamentIds,
  stats,
  allCharacters,
  title,
}: CharacterDetailViewProps) {
  const router = useRouter();

  const handleBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      if (mode === "cross") {
        router.push("/");
      } else {
        router.push(`/tournament/${tournamentId || ""}`);
      }
    }
  };

  const c = allCharacters.find(x => x.id === characterId);
  if (!c) {
    return (
      <main className="p-6 md:p-12 max-w-4xl mx-auto">
        <p className="text-slate-400 text-center py-12">キャラクターが見つかりません (ID: {characterId})</p>
        <div className="text-center">
          <button
            type="button"
            onClick={handleBack}
            className="inline-flex items-center space-x-2 text-blue-400 hover:text-blue-300 font-bold transition-colors cursor-pointer"
          >
            <ChevronLeft size={18} />
            <span>前のページに戻る</span>
          </button>
        </div>
      </main>
    );
  }

  const usageData = stats?.character_usage?.find((x: any) => x.id === characterId || x.character_id === characterId);
  const usageCount = usageData?.count || 0;
  const winRate = usageData?.win_rate || 0;
  const charWins = usageData?.win_count || 0;
  const totalMatches = usageData?.total_matches || 0;
  const charLosses = totalMatches - charWins;
  const hasPositionStats = Array.isArray(usageData?.position_stats) && usageData.position_stats.length > 0;
  const hasTeamPositionStats = Array.isArray(usageData?.team_position_stats) && usageData.team_position_stats.length > 0;
  const relatedTeams = stats?.team_usage?.filter((t: any) => (t.character_ids || []).includes(characterId)) || [];

  // シナジー（一緒によく編成されるキャラクター）の集計
  const synergyCounts: Record<number, number> = {};
  relatedTeams.forEach((t: any) => {
    (t.character_ids || []).forEach((cid: number) => {
      if (cid !== characterId) {
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
    .sort((a, b) => b.synergyCount - a.synergyCount);

  const burst1Chars = synergisticChars.filter(ch => ch.burst_phase === "1");
  const burst2Chars = synergisticChars.filter(ch => ch.burst_phase === "2");
  const burst3Chars = synergisticChars.filter(ch => ch.burst_phase === "3");

  // 編成表示コンポーネント
  const TeamDisplay = ({ charIds }: { charIds: number[] }) => {
    const displayChars = charIds.map(cid => allCharacters.find(ch => ch.id === cid)).filter(Boolean);
    return (
      <div className="flex space-x-2">
        {displayChars.map((ch: any, i: number) => {
          const teamMemberCharacterId = ch.id;
          const href = mode === "cross"
            ? `/character/${teamMemberCharacterId}?tournaments=${tournamentIds?.join(',') || ''}`
            : `/tournament/${tournamentId}/dashboard/character/${teamMemberCharacterId}`;
          return (
            <Link
              key={i}
              href={href}
              className="flex flex-col items-center space-y-1 group"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="w-10 h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 group-hover:ring-blue-500 overflow-hidden flex items-center justify-center transition-all">
                {ch?.is_template_available ? (
                  <img src={`/api/char-icon/${ch.id}.png`} loading="lazy" decoding="async" alt={ch?.name || "不明"} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-[10px] text-slate-500 font-bold leading-tight text-center">{ch?.name?.slice(0, 3) || "不明"}</span>
                )}
              </div>
              <span className="text-[9px] text-slate-400 w-10 truncate text-center" title={ch?.name || "不明"}>{ch?.name || "不明"}</span>
            </Link>
          );
        })}
      </div>
    );
  };

  // 成績カラーマップ
  const resultColors: Record<string, string> = {
    "優勝": "bg-amber-400/20 text-amber-300 ring-amber-400/50",
    "準優勝": "bg-slate-300/20 text-slate-200 ring-slate-300/50",
    "ベスト4": "bg-orange-500/20 text-orange-400 ring-orange-500/50",
    "ベスト8": "bg-blue-500/20 text-blue-400 ring-blue-500/50",
    "ベスト16": "bg-purple-500/20 text-purple-400 ring-purple-500/50",
    "ベスト32": "bg-slate-700/60 text-slate-400 ring-slate-600/50",
    "ベスト64": "bg-slate-800/60 text-slate-500 ring-slate-700/50",
  };

  return (
    <main className="p-6 md:p-12 max-w-4xl mx-auto space-y-8 pb-24">
      {/* ナビゲーション */}
      <div className="flex items-center space-x-4">
        <button
          type="button"
          onClick={handleBack}
          className="p-2 bg-slate-800 hover:bg-slate-700 rounded-full transition-colors cursor-pointer ring-1 ring-white/10 shadow-lg"
          aria-label="前のページに戻る"
        >
          <ChevronLeft size={24} className="text-slate-300" />
        </button>
        <div className="flex-1">
          <p className="text-slate-500 text-xs font-bold uppercase tracking-wider">
            {title}
          </p>
          <h1 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">
            {c.name}
          </h1>
        </div>
      </div>

      {/* 横断モードバッジ */}
      {mode === "cross" && tournamentIds && (
        <div className="bg-cyan-500/10 px-4 py-2 rounded-xl ring-1 ring-cyan-500/30 flex items-center space-x-2">
          <span className="text-[10px] font-black text-cyan-400">横断モード: {tournamentIds.length}大会の統合データ</span>
        </div>
      )}

      {/* プロフィールヘッダー */}
      <div className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-8 rounded-3xl shadow-2xl">
        <div className="flex items-center space-x-6 mb-8">
          <div className="w-28 h-28 rounded-2xl bg-slate-800 ring-2 ring-blue-500 overflow-hidden shadow-xl flex items-center justify-center shrink-0">
            {c.is_template_available ? (
              <img src={`/api/char-icon/${c.id}.png`} loading="lazy" decoding="async" alt={c.name} className="w-full h-full object-cover" />
            ) : (
              <span className="text-3xl text-slate-500 font-black">{c.name.slice(0, 3)}</span>
            )}
          </div>
          <div>
            <h2 className="text-4xl font-black text-white mb-3">{c.name}</h2>
            <div className="flex flex-wrap gap-2">
              <span className="px-3 py-1 bg-slate-800 text-slate-300 font-bold rounded-lg ring-1 ring-white/10 text-sm">
                {c.rarity || "不明"}
              </span>
              {c.element && (
                <span className="px-3 py-1 bg-slate-800 text-slate-300 font-bold rounded-lg ring-1 ring-white/10 text-sm">
                  {c.element}
                </span>
              )}
              {c.manufacturer && (
                <span className="px-3 py-1 bg-slate-800 text-slate-300 font-bold rounded-lg ring-1 ring-white/10 text-sm">
                  {c.manufacturer}
                </span>
              )}
              {c.burst_phase && (
                <span className="px-3 py-1 bg-slate-800 text-slate-300 font-bold rounded-lg ring-1 ring-white/10 text-sm">
                  Burst {c.burst_phase}
                </span>
              )}
              {c.weapon && (
                <span className="px-3 py-1 bg-slate-800 text-slate-300 font-bold rounded-lg ring-1 ring-white/10 text-sm">
                  {c.weapon}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* 統計カード */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-blue-500/10 p-5 rounded-2xl ring-1 ring-blue-500/20 flex flex-col items-center justify-center">
            <p className="text-blue-400 text-xs font-bold mb-1">大会採用数</p>
            <p className="text-3xl font-black text-blue-400">{usageCount} <span className="text-lg">回</span></p>
          </div>
          <div className="bg-emerald-500/10 p-5 rounded-2xl ring-1 ring-emerald-500/20 flex flex-col items-center justify-center">
            <p className="text-emerald-400 text-xs font-bold mb-1">勝率 (非ミラー)</p>
            <p className="text-3xl font-black text-emerald-400">{winRate}<span className="text-lg">%</span></p>
          </div>
          <div className="bg-green-500/10 p-5 rounded-2xl ring-1 ring-green-500/20 flex flex-col items-center justify-center">
            <p className="text-green-400 text-xs font-bold mb-1">勝利数</p>
            <p className="text-3xl font-black text-green-400">{charWins}</p>
          </div>
          <div className="bg-slate-700/30 p-5 rounded-2xl ring-1 ring-white/10 flex flex-col items-center justify-center">
            <p className="text-slate-400 text-xs font-bold mb-1">敗北数</p>
            <p className="text-3xl font-black text-slate-400">{charLosses}</p>
          </div>
        </div>
      </div>

      {/* よく一緒に編成されるキャラクター */}
      <div className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-8 rounded-3xl shadow-2xl space-y-4">
        <h3 className="text-xl font-black text-white flex items-center space-x-2">
          <Users size={20} className="text-slate-400" />
          <span>よく一緒に編成されるキャラクター</span>
        </h3>
        
        <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-hidden divide-y divide-white/5">
          {/* Burst 1 */}
          <div className="flex flex-col md:flex-row">
            <div className="md:w-32 bg-slate-800/80 p-4 flex items-center justify-center shrink-0 border-b md:border-b-0 md:border-r border-white/5">
              <span className="font-black text-slate-300 tracking-wider">BURST 1</span>
            </div>
            <div className="p-4 flex flex-wrap gap-4 flex-1">
              {burst1Chars.map(synergyChar => {
                const synergyCharacterId = synergyChar.id;
                const synergyHref = mode === "cross"
                  ? `/character/${synergyCharacterId}?tournaments=${tournamentIds?.join(',') || ''}`
                  : `/tournament/${tournamentId}/dashboard/character/${synergyCharacterId}`;
                return (
                  <Link
                    key={synergyCharacterId}
                    href={synergyHref}
                    className="flex flex-col items-center space-y-2 group p-2 rounded-xl hover:bg-slate-700/50 transition-colors cursor-pointer"
                  >
                    <div className="w-12 h-12 rounded-xl bg-slate-800 ring-1 ring-white/10 group-hover:ring-blue-500 overflow-hidden flex items-center justify-center transition-all">
                      {synergyChar.is_template_available ? (
                        <img src={`/api/char-icon/${synergyChar.id}.png`} loading="lazy" decoding="async" alt={synergyChar.name} className="w-full h-full object-cover" />
                      ) : (
                        <span className="text-[10px] text-slate-500 font-bold">{synergyChar.name?.slice(0, 3)}</span>
                      )}
                    </div>
                    <div className="flex flex-col items-center">
                      <span className="text-[10px] text-slate-300 w-16 truncate text-center font-bold" title={synergyChar.name}>{synergyChar.name}</span>
                      <span className="text-[10px] text-emerald-400 font-bold bg-emerald-400/10 px-1.5 py-0.5 rounded-full mt-1">
                        {synergyChar.synergyCount}回 ({usageCount > 0 ? Math.round((synergyChar.synergyCount / usageCount) * 100) : 0}%)
                      </span>
                    </div>
                  </Link>
                );
              })}
              {burst1Chars.length === 0 && <span className="text-slate-500 text-sm p-2 flex items-center">該当なし</span>}
            </div>
          </div>

          {/* Burst 2 */}
          <div className="flex flex-col md:flex-row">
            <div className="md:w-32 bg-slate-800/80 p-4 flex items-center justify-center shrink-0 border-b md:border-b-0 md:border-r border-white/5">
              <span className="font-black text-slate-300 tracking-wider">BURST 2</span>
            </div>
            <div className="p-4 flex flex-wrap gap-4 flex-1">
              {burst2Chars.map(synergyChar => {
                const synergyCharacterId = synergyChar.id;
                const synergyHref = mode === "cross"
                  ? `/character/${synergyCharacterId}?tournaments=${tournamentIds?.join(',') || ''}`
                  : `/tournament/${tournamentId}/dashboard/character/${synergyCharacterId}`;
                return (
                  <Link
                    key={synergyCharacterId}
                    href={synergyHref}
                    className="flex flex-col items-center space-y-2 group p-2 rounded-xl hover:bg-slate-700/50 transition-colors cursor-pointer"
                  >
                    <div className="w-12 h-12 rounded-xl bg-slate-800 ring-1 ring-white/10 group-hover:ring-emerald-500 overflow-hidden flex items-center justify-center transition-all">
                      {synergyChar.is_template_available ? (
                        <img src={`/api/char-icon/${synergyChar.id}.png`} loading="lazy" decoding="async" alt={synergyChar.name} className="w-full h-full object-cover" />
                      ) : (
                        <span className="text-[10px] text-slate-500 font-bold">{synergyChar.name?.slice(0, 3)}</span>
                      )}
                    </div>
                    <div className="flex flex-col items-center">
                      <span className="text-[10px] text-slate-300 w-16 truncate text-center font-bold" title={synergyChar.name}>{synergyChar.name}</span>
                      <span className="text-[10px] text-emerald-400 font-bold bg-emerald-400/10 px-1.5 py-0.5 rounded-full mt-1">
                        {synergyChar.synergyCount}回 ({usageCount > 0 ? Math.round((synergyChar.synergyCount / usageCount) * 100) : 0}%)
                      </span>
                    </div>
                  </Link>
                );
              })}
              {burst2Chars.length === 0 && <span className="text-slate-500 text-sm p-2 flex items-center">該当なし</span>}
            </div>
          </div>

          {/* Burst 3 */}
          <div className="flex flex-col md:flex-row">
            <div className="md:w-32 bg-slate-800/80 p-4 flex items-center justify-center shrink-0 border-r border-white/5">
              <span className="font-black text-slate-300 tracking-wider">BURST 3</span>
            </div>
            <div className="p-4 flex flex-wrap gap-4 flex-1">
              {burst3Chars.map(synergyChar => {
                const synergyCharacterId = synergyChar.id;
                const synergyHref = mode === "cross"
                  ? `/character/${synergyCharacterId}?tournaments=${tournamentIds?.join(',') || ''}`
                  : `/tournament/${tournamentId}/dashboard/character/${synergyCharacterId}`;
                return (
                  <Link
                    key={synergyCharacterId}
                    href={synergyHref}
                    className="flex flex-col items-center space-y-2 group p-2 rounded-xl hover:bg-slate-700/50 transition-colors cursor-pointer"
                  >
                    <div className="w-12 h-12 rounded-xl bg-slate-800 ring-1 ring-white/10 group-hover:ring-amber-500 overflow-hidden flex items-center justify-center transition-all">
                      {synergyChar.is_template_available ? (
                        <img src={`/api/char-icon/${synergyChar.id}.png`} loading="lazy" decoding="async" alt={synergyChar.name} className="w-full h-full object-cover" />
                      ) : (
                        <span className="text-[10px] text-slate-500 font-bold">{synergyChar.name?.slice(0, 3)}</span>
                      )}
                    </div>
                    <div className="flex flex-col items-center">
                      <span className="text-[10px] text-slate-300 w-16 truncate text-center font-bold" title={synergyChar.name}>{synergyChar.name}</span>
                      <span className="text-[10px] text-emerald-400 font-bold bg-emerald-400/10 px-1.5 py-0.5 rounded-full mt-1">
                        {synergyChar.synergyCount}回 ({usageCount > 0 ? Math.round((synergyChar.synergyCount / usageCount) * 100) : 0}%)
                      </span>
                    </div>
                  </Link>
                );
              })}
              {burst3Chars.length === 0 && <span className="text-slate-500 text-sm p-2 flex items-center">該当なし</span>}
            </div>
          </div>
        </div>
      </div>

      {/* 配置ポジション分析 */}
      {hasPositionStats && (
        <div className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-8 rounded-3xl shadow-2xl space-y-4">
          <h3 className="text-xl font-black text-white flex items-center space-x-2">
            <span className="text-lg">📊</span>
            <span>部隊内の配置傾向</span>
          </h3>
          <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-hidden">
            <table className="w-full text-center">
              <thead>
                <tr className="border-b border-white/10">
                  {[1, 2, 3, 4, 5].map(p => (
                    <th key={p} className="py-4 px-4 text-slate-400 font-black text-xl">{p}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {/* 配置回数（割合） */}
                <tr className="border-b border-white/5">
                  {usageData.position_stats.map((ps: any) => (
                    <td key={ps.position} className="py-4 px-4">
                      <span className="text-white font-bold text-2xl">{ps.count}</span>
                      <span className="text-slate-500 text-sm ml-0.5">回</span>
                      <br />
                      <span className="text-slate-400 text-sm">({ps.pct}%)</span>
                    </td>
                  ))}
                </tr>
                {/* ポジション別勝率 */}
                <tr>
                  {usageData.position_stats.map((ps: any) => (
                    <td key={ps.position} className="py-4 px-4">
                      {ps.win_rate !== null ? (
                        <>
                          <span className={`font-black text-2xl ${ps.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                            {ps.win_rate}%
                          </span>
                          <br />
                          <span className="text-slate-500 text-xs">{ps.wins}W {ps.total - ps.wins}L</span>
                        </>
                      ) : (
                        <span className="text-slate-600 text-sm">-</span>
                      )}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
            <div className="px-4 py-3 bg-slate-900/50 border-t border-white/5 flex justify-between text-xs text-slate-500">
              <span>上段: 配置回数（割合）</span>
              <span>下段: そのポジションでの勝率</span>
            </div>
          </div>
        </div>
      )}

      {/* 編成の配置傾向 */}
      {hasTeamPositionStats && (
        <div className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-8 rounded-3xl shadow-2xl space-y-4">
          <h3 className="text-xl font-black text-white flex items-center space-x-2">
            <span className="text-lg">📊</span>
            <span>編成の配置傾向</span>
          </h3>
          <div className="bg-slate-800/50 rounded-xl ring-1 ring-white/10 overflow-hidden">
            <table className="w-full text-center">
              <thead>
                <tr className="border-b border-white/10 bg-slate-900/50">
                  <th className="py-4 px-4 text-slate-400 font-bold text-sm">〇番目</th>
                  <th className="py-4 px-4 text-slate-400 font-bold text-sm">採用数</th>
                  <th className="py-4 px-4 text-slate-400 font-bold text-sm">勝率</th>
                  <th className="py-4 px-4 text-slate-400 font-bold text-sm">最終成績</th>
                </tr>
              </thead>
              <tbody>
                {[1, 2, 3, 4, 5].map(pos => {
                  const ps = usageData.team_position_stats.find((p:any) => p.position === pos) || { count: 0, pct: 0, wins: 0, total: 0, win_rate: null, best_result: null };
                  return (
                    <tr key={pos} className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors">
                      <td className="py-4 px-4 text-white font-black text-lg">{pos}番目</td>
                      <td className="py-4 px-4">
                        <span className="text-white font-bold text-xl">{ps.count}</span>
                        <span className="text-slate-500 text-sm ml-0.5">人</span>
                        <br />
                        <span className="text-slate-400 text-sm">({ps.pct}%)</span>
                      </td>
                      <td className="py-4 px-4">
                        {ps.win_rate !== null ? (
                          <>
                            <span className={`font-black text-xl ${ps.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                              {ps.win_rate}%
                            </span>
                            <br />
                            <span className="text-slate-500 text-xs">{ps.wins}W {ps.total - ps.wins}L</span>
                          </>
                        ) : (
                          <span className="text-slate-600 text-sm">対戦なし</span>
                        )}
                      </td>
                      <td className="py-4 px-4">
                        {ps.best_result ? (
                          <span className={`inline-block px-3 py-1 text-sm font-bold rounded-full ring-1 ${
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
                          <span className="text-slate-600 text-sm">-</span>
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

      {/* 採用されている編成リスト */}
      <div className="bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-8 rounded-3xl shadow-2xl space-y-6">
        <h3 className="text-xl font-black text-white flex items-center space-x-2">
          <Users size={20} className="text-slate-400" />
          <span>採用されている編成リスト</span>
          <span className="text-sm font-bold text-slate-500 ml-2">({relatedTeams.length}件)</span>
        </h3>

        <div className="space-y-3">
          {[...relatedTeams]
            .sort((a: any, b: any) => {
              const resultScores: Record<string, number> = {
                "優勝": 1, "準優勝": 2, "ベスト4": 4,
                "ベスト8": 8, "ベスト16": 16, "ベスト32": 32, "ベスト64": 64
              };
              const sa = resultScores[a.best_result] ?? 999;
              const sb = resultScores[b.best_result] ?? 999;
              return sa !== sb ? sa - sb : b.win_rate - a.win_rate;
            })
            .map((team: any, idx: number) => {
              const teamResultClass = resultColors[team.best_result] ?? "bg-slate-800/60 text-slate-500 ring-slate-700/50";
              return (
                <div
                  key={idx}
                  onClick={() => {
                    if (mode === "cross") {
                      const tIds = team.character_ids || team.characters?.map((c:any) => c.id) || [];
                      const tKey = tIds.length > 0 ? [...tIds].map(Number).sort((a, b) => a - b).join("-") : team.canonical_id;
                      router.push(`/?tab=matchups&teamKey=${encodeURIComponent(tKey)}&team=${encodeURIComponent(tKey)}&tournaments=${tournamentIds?.join(',') || ''}`);
                    } else {
                      router.push(`/tournament/${tournamentId}/dashboard?tab=matchups&team=${encodeURIComponent(team.canonical_id)}`);
                    }
                  }}
                  className="flex flex-col bg-slate-800/50 hover:bg-slate-700/60 transition-colors p-5 rounded-xl ring-1 ring-white/5 hover:ring-purple-500/30 space-y-3 cursor-pointer"
                >
                  {/* 編成アイコン行 */}
                  <div className="flex items-center justify-between">
                    <TeamDisplay charIds={team.character_ids || []} />
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
            <p className="text-slate-500 text-sm text-center py-8">このキャラクターを含む編成データがありません</p>
          )}
        </div>
      </div>

      {/* フッターナビゲーション */}
      <div className="text-center pt-4">
        <button
          type="button"
          onClick={handleBack}
          className="inline-flex items-center space-x-2 text-blue-400 hover:text-blue-300 font-bold transition-colors cursor-pointer"
        >
          <ChevronLeft size={18} />
          <span>前のページに戻る</span>
        </button>
      </div>
    </main>
  );
}
