"use client";
import { useEffect, useMemo, useState } from "react";
import { ArenaResult, ArenaTournament, arenaResultLabels, calculateChampionArenaStats, CHAMPION_ARENA_STORAGE_KEY, loadUserData, UserDataV1 } from "../../../lib/championArenaResults";

const choices = Object.entries(arenaResultLabels) as [ArenaResult,string][];

export default function ChampionArenaResultsPage() {
  const [tournaments,setTournaments]=useState<ArenaTournament[]>([]);
  const [data,setData]=useState<UserDataV1|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{ setData(loadUserData(window.localStorage)); },[]);
  useEffect(()=>{ const controller=new AbortController(); const api=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
    fetch(`${api}/api/champion-arena/tournaments`,{signal:controller.signal}).then(async response=>{if(!response.ok)throw new Error();setTournaments(await response.json());}).catch(reason=>{if(reason?.name!=="AbortError")setError("大会一覧を取得できませんでした。");}); return()=>controller.abort(); },[]);
  const stats=useMemo(()=>calculateChampionArenaStats(tournaments,data?.championArena.results??{}),[tournaments,data]);
  const update=(tournament:ArenaTournament,result:ArenaResult)=>setData(current=>{
    const next=current??{version:1 as const,championArena:{results:{}}};
    const updated={...next,championArena:{results:{...next.championArena.results,[String(tournament.id)]:{result,titleSnapshot:tournament.title}}}};
    window.localStorage.setItem(CHAMPION_ARENA_STORAGE_KEY,JSON.stringify(updated)); return updated;
  });
  return <main className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100"><div className="mx-auto max-w-4xl space-y-6">
    <header><h1 className="text-3xl font-black">チャンアリ戦績</h1><p className="mt-2 text-sm text-slate-400">入力内容はこのブラウザだけに保存され、サーバーには送信されません。</p></header>
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      <Stat label="出場回数" value={`${stats.appearanceCount}回`}/><Stat label="最高成績" value={stats.bestResult?arenaResultLabels[stats.bestResult]:"－"}/>
      <Stat label="最新成績" value={stats.latest?`${stats.latest.tournament.title}：${stats.latest.result==="unknown"?"成績不明":arenaResultLabels[stats.latest.result]}`:"－"}/>
      <Stat label="成績判明" value={`${stats.knownCount} / ${stats.appearanceCount}`}/><Stat label="不明" value={String(stats.unknownCount)}/>
    </section>
    {error&&<p role="alert" className="rounded border border-red-700 p-3 text-red-300">{error}</p>}
    <section className="space-y-3">{tournaments.map(tournament=><label key={tournament.id} className="block rounded-xl border border-slate-800 bg-slate-900 p-4">
      <span className="mb-2 block font-bold">{tournament.title}</span><select aria-label={`${tournament.title}の成績`} value={data?.championArena.results[String(tournament.id)]?.result??"not_entered"} onChange={event=>update(tournament,event.target.value as ArenaResult)} className="w-full rounded border border-slate-700 bg-slate-950 p-3">{choices.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select>
    </label>)}</section>
  </div></main>;
}
function Stat({label,value}:{label:string;value:string}){return <div className="rounded-xl border border-slate-800 bg-slate-900 p-4"><div className="text-xs text-slate-400">{label}</div><div className="mt-1 font-bold">{value}</div></div>}
