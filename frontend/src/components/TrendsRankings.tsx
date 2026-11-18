"use client";
import {useEffect,useState} from "react";
import {useI18n} from "@/i18n/I18nProvider";
import CharacterUsageByResultRanking from "./CharacterUsageByResultRanking";
import TeamAdoptionRanking from "./TeamAdoptionRanking";
import {WIN_RATE_FILTER_CLASS} from "./TeamStatisticsMeaning";

type Props={formal:boolean;tournamentIds:number[];privateTournamentId?:number;allCharacters:any[];onSelectCharacter:(id:number)=>void;onTeamClick:(id:string,team:any)=>void};
export default function TrendsRankings({formal,tournamentIds,privateTournamentId,allCharacters,onSelectCharacter,onTeamClick}:Props){
 const {t}=useI18n();
 const [stage,setStage]=useState("championship");
 const [finish,setFinish]=useState("best8");
 const [data,setData]=useState<any>(null);
 const [error,setError]=useState(false);
 const [visible,setVisible]=useState(10);
 const idsKey=[...tournamentIds].sort((a,b)=>a-b).join(",");
 useEffect(()=>{
  const controller=new AbortController();setData(null);setError(false);setVisible(10);
  if(!idsKey)return ()=>controller.abort();
  const phase=formal?stage:"legacy";
  const result=formal?"all":finish;
  const url=privateTournamentId?`/api/tournaments/${privateTournamentId}/dashboard/stats?registration_phase=${phase}&trends_result=${result}`:"/api/dashboard/cross-tournament/stats";
  fetch(url,{signal:controller.signal,cache:"no-store",...(privateTournamentId?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tournament_ids:idsKey.split(",").map(Number),registration_phase:phase,trends_result:result})})})
   .then(async response=>{if(!response.ok)throw new Error("Trends request failed");return response.json();})
   .then(value=>{if(!controller.signal.aborted)setData(value);})
   .catch(()=>{if(!controller.signal.aborted)setError(true);});
  return ()=>controller.abort();
 },[idsKey,privateTournamentId,formal,stage,finish]);
 return <div className="space-y-10">
  <div className="rounded-xl bg-slate-800/60 p-4 ring-1 ring-blue-400/30">
   {formal?<select aria-label={t("teamMeaning.registrationPhase")} className={WIN_RATE_FILTER_CLASS} value={stage} onChange={event=>setStage(event.target.value)}>{["league","championship","final"].map(value=><option key={value} value={value}>{t("teamMeaning.filterValue",{label:t("teamMeaning.registrationPhase"),value:t(`arenaPhases.${value}`)})}</option>)}</select>
   :<select aria-label={t("teamMeaning.commanderResults")} className={WIN_RATE_FILTER_CLASS} value={finish} onChange={event=>setFinish(event.target.value)}>{["all","best16","best8","best4","runner_up","champion"].map(value=><option key={value} value={value}>{t("teamMeaning.filterValue",{label:t("teamMeaning.commanderResults"),value:value==="all"?t("common.all"):t(`trends.result.${value}`)})}</option>)}</select>}
  </div>
  {error?<p role="alert">{t("arenaPhases.error")}</p>:!data?<p role="status">{t("common.loading")}</p>:<>
   <CharacterUsageByResultRanking stats={data} allCharacters={allCharacters} onSelectCharacter={id=>{const phase=formal?stage:"legacy";window.location.assign(privateTournamentId?`/tournament/${privateTournamentId}/dashboard/character/${id}?registration_phase=${phase}`:`/character/${id}?tournaments=${idsKey}&registration_phase=${phase}`);}}/>
   <TeamAdoptionRanking title={t("trends.teams")} teams={data.team_usage ?? []} totalRegisteredPlayers={data.total_players ?? 0} visibleCount={visible} onShowMore={()=>setVisible(value=>value+15)} allCharacters={allCharacters} onTeamClick={onTeamClick}/>
  </>}
 </div>;
}
