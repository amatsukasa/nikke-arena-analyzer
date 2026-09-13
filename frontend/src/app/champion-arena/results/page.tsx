"use client";
import { useEffect, useMemo, useState } from "react";
import { ArenaResult, ArenaTournament, calculateChampionArenaStats, CHAMPION_ARENA_STORAGE_KEY, loadUserData, UserDataV1 } from "../../../lib/championArenaResults";
import { useI18n } from "@/i18n/I18nProvider";

const choices: ArenaResult[] = ["not_entered", "not_participated", "unknown", "league_loss", "best64", "best32", "best16", "best8", "best4", "runner_up", "champion"];
const resultKeys: Record<ArenaResult, string> = {
  not_entered: "championArena.result.notEntered",
  not_participated: "championArena.result.notParticipated",
  unknown: "championArena.result.unknown",
  league_loss: "championArena.result.leagueLoss",
  best64: "championArena.result.best64",
  best32: "championArena.result.best32",
  best16: "championArena.result.best16",
  best8: "championArena.result.best8",
  best4: "championArena.result.best4",
  runner_up: "championArena.result.runnerUp",
  champion: "championArena.result.champion",
};

export default function ChampionArenaResultsPage() {
  const { t } = useI18n();
  const [tournaments,setTournaments]=useState<ArenaTournament[]>([]);
  const [data,setData]=useState<UserDataV1|null>(null);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  useEffect(()=>{ setData(loadUserData(window.localStorage)); },[]);
  useEffect(()=>{ const controller=new AbortController(); const api=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
    fetch(`${api}/api/champion-arena/tournaments`,{signal:controller.signal}).then(async response=>{if(!response.ok)throw new Error();setTournaments(await response.json());}).catch(reason=>{if(reason?.name!=="AbortError")setError(t("championArena.loadError"));}).finally(()=>setLoading(false)); return()=>controller.abort(); },[t]);
  const stats=useMemo(()=>calculateChampionArenaStats(tournaments,data?.championArena.results??{}),[tournaments,data]);
  const update=(tournament:ArenaTournament,result:ArenaResult)=>setData(current=>{
    const next=current??{version:1 as const,championArena:{results:{}}};
    const updated={...next,championArena:{results:{...next.championArena.results,[String(tournament.id)]:{result,titleSnapshot:tournament.title}}}};
    window.localStorage.setItem(CHAMPION_ARENA_STORAGE_KEY,JSON.stringify(updated)); return updated;
  });
  return <main className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100"><div className="mx-auto max-w-4xl space-y-6">
    <header><h1 className="text-3xl font-black">{t("championArena.title")}</h1><p className="mt-2 text-sm text-slate-400">{t("championArena.description")}</p></header>
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      <Stat label={t("championArena.appearanceCount")} value={t("championArena.appearanceCountValue",{count:stats.appearanceCount})}/><Stat label={t("championArena.bestResult")} value={stats.bestResult?t(resultKeys[stats.bestResult]):"－"}/>
      <Stat label={t("championArena.latestResult")} value={stats.latest?t("championArena.latestResultValue",{tournament:stats.latest.tournament.title,result:t(resultKeys[stats.latest.result])}):"－"}/>
      <Stat label={t("championArena.knownResults")} value={t("championArena.knownResultsValue",{known:stats.knownCount,total:stats.appearanceCount})}/><Stat label={t("championArena.unknownCount")} value={String(stats.unknownCount)}/>
    </section>
    {error&&<p role="alert" className="rounded border border-red-700 p-3 text-red-300">{error}</p>}
    {loading&&<p className="text-slate-400">{t("common.loading")}</p>}
    {!loading&&!error&&tournaments.length===0&&<p className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-slate-400">{t("championArena.noTournaments")}</p>}
    <section className="space-y-3">{tournaments.map(tournament=><label key={tournament.id} className="block rounded-xl border border-slate-800 bg-slate-900 p-4">
      <span className="mb-2 block font-bold">{tournament.title}</span><select aria-label={t("championArena.resultAria",{tournament:tournament.title})} value={data?.championArena.results[String(tournament.id)]?.result??"not_entered"} onChange={event=>update(tournament,event.target.value as ArenaResult)} className="w-full rounded border border-slate-700 bg-slate-950 p-3">{choices.map(value=><option key={value} value={value}>{t(resultKeys[value])}</option>)}</select>
    </label>)}</section>
  </div></main>;
}
function Stat({label,value}:{label:string;value:string}){return <div className="rounded-xl border border-slate-800 bg-slate-900 p-4"><div className="text-xs text-slate-400">{label}</div><div className="mt-1 font-bold">{value}</div></div>}
