"use client";

import TeamDisplay from "./TeamDisplay";
import { adoptionDisplay } from "@/lib/adoptionRate";
import { tournamentResultClass, tournamentResultLabel } from "@/lib/tournamentResult";

type Props = { teams: any[]; totalRegisteredPlayers: number; visibleCount: number; onShowMore: () => void; allCharacters: any[]; onTeamClick: (canonicalId: string, team: any) => void };

export default function TeamAdoptionRanking({ teams, totalRegisteredPlayers, visibleCount, onShowMore, allCharacters, onTeamClick }: Props) {
  return <section>
    <h2 className="mb-6 text-xl font-bold text-white">編成（5名組み合わせ）登録データ内採用率ランキング</h2>
    <div className="space-y-3">
      <div className="hidden grid-cols-12 gap-4 rounded-xl border border-white/5 bg-slate-900/80 px-6 py-3 text-xs font-bold text-slate-400 md:grid">
        <div className="col-span-5">編成</div><div className="col-span-3 text-center">採用率</div><div className="col-span-2 text-center">最終成績</div><div className="col-span-2 text-right">勝率</div>
      </div>
      {teams.slice(0, visibleCount).map((team, index) => {
        const adoption = adoptionDisplay(team, totalRegisteredPlayers);
        const result = tournamentResultLabel(team.best_result);
        return <button key={team.canonical_id ?? index} type="button" onClick={() => onTeamClick(team.canonical_id, team)} className="grid w-full grid-cols-1 gap-4 rounded-xl bg-slate-800/40 p-4 text-left ring-1 ring-white/5 transition-colors hover:bg-slate-700/50 md:grid-cols-12 md:items-center md:px-6">
          <div className="min-w-0 md:col-span-5"><TeamDisplay charIds={team.character_ids ?? team.characters?.map((character: any) => character.id) ?? []} allCharacters={allCharacters} /></div>
          <div className="md:col-span-3 md:text-center"><div className="text-2xl font-black text-emerald-300">{adoption.adoptionRate.toFixed(1)}%</div><div className="text-xs font-bold text-slate-400">{adoption.totalRegisteredPlayers}人中{adoption.playerCount}人</div></div>
          <div className="md:col-span-2 md:text-center">{result ? <span className={`inline-block rounded-full px-3 py-1 text-xs font-bold ring-1 ${tournamentResultClass(result)}`}>{result}</span> : <span className="text-xs text-slate-500">データなし</span>}</div>
          <div className="md:col-span-2 md:text-right">{team.total_matches > 0 ? <><div className="text-lg font-black text-white">{Number(team.win_rate ?? team.win_count / team.total_matches * 100).toFixed(1)}%</div><div className="text-xs text-slate-500">{team.win_count}W {team.total_matches - team.win_count}L</div></> : <span className="text-xs text-slate-600">対戦なし</span>}</div>
        </button>;
      })}
      {teams.length === 0 && <div className="rounded-xl bg-slate-900/50 p-8 text-center text-slate-500">データがありません</div>}
      {teams.length > visibleCount && <button type="button" onClick={onShowMore} className="w-full rounded-xl bg-slate-800/80 py-3 text-sm font-bold text-slate-300 ring-1 ring-white/10 hover:bg-slate-700">もっと見る (残りを表示)</button>}
    </div>
  </section>;
}
