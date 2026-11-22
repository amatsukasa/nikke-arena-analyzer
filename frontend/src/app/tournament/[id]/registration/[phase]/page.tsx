"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import Link from "@/components/LocalizedLink";
import DeckRegistrationEditor from "@/components/DeckRegistrationEditor";
import DeckRegistrationViewer from "@/components/DeckRegistrationViewer";
import DeckRegistrationViewport from "@/components/DeckRegistrationViewport";
import { usePrivatePlayerNames } from "@/hooks/usePrivatePlayerNames";
import PrivatePlayerNameEditor from "@/components/PrivatePlayerNameEditor";
import { useAuth } from "@/context/AuthContext";
import { useCharacterCatalog } from "@/hooks/useCharacterCatalog";
import { analyzeRegistrationDecks, saveRegistrationDecks } from "@/lib/deckRegistrationApi";
import { RegistrationTeam } from "@/lib/deckRegistration";
import { registrationStage } from "@/lib/registrationStage";
import { useI18n } from "@/i18n/I18nProvider";

type Phase = "initial" | "best8" | "final";
type Registration = {player_id:number;phase:Phase;eligible:boolean;qualification:string|null;revision_id:number|null;complete:boolean;teams:RegistrationTeam[]};
type PhaseState = {format:"full_64"|"champion_8";players:{id:number;name:string;seed_number:number|null;icon_url:string|null}[];registrations:Registration[]};
const blankTeams = ():RegistrationTeam[] => Array.from({length:5},(_,index)=>({team_number:index+1,characters:Array.from({length:5},()=>({id:null,collection_level:null}))}));

export default function PhaseRegistrationPage(){
  const params=useParams(); const search=useSearchParams(); const {t}=useI18n(); const {user,isLoading}=useAuth();
  const requestedPlayer=search.get("player");
  const requestedPlayerId=requestedPlayer==null?null:/^[1-9]\d*$/.test(requestedPlayer)?Number(requestedPlayer):NaN;
  const tournamentId=Number(params.id);const phase=String(params.phase);const {characters,refreshCharacters}=useCharacterCatalog<any>();
  const privateNames=usePrivatePlayerNames(tournamentId);
  const [tournament,setTournament]=useState<{name:string;created_by:number;publication_status:string;deck_registration_phases:boolean}|null>(null);
  const [data,setData]=useState<PhaseState|null>(null);const [playerId,setPlayerId]=useState<number|null>(null);
  const [teams,setTeams]=useState<RegistrationTeam[]>([]);const [editing,setEditing]=useState(false);const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState<""|"analysis"|"teams">("");const [error,setError]=useState("");const [history,setHistory]=useState<{id:number;player_id:number;phase:Phase;teams:RegistrationTeam[]}[]>([]);
  const base=`/api/tournaments/${tournamentId}/arena-phases`;
  const back=`/tournament/${tournamentId}${data?.format==="full_64"||search.get("returnTab")==="champion"?"?tab=champion":""}`;
  const writable=Boolean(user&&tournament&&tournament.publication_status!=="published"&&(user.role==="admin"||user.id===tournament.created_by));
  const eligible=data?.registrations.filter(r=>r.phase===phase&&r.eligible)||[];const entry=eligible.find(r=>r.player_id===playerId);const player=data?.players.find(p=>p.id===playerId);
  useEffect(()=>{
    const controller=new AbortController();setError("");setData(null);setTournament(null);setPlayerId(null);setHistory([]);setEditing(false);setDirty(false);
    if(!Number.isInteger(tournamentId)||tournamentId<=0||!["best8","final"].includes(phase)){setError(t("arenaPhases.invalidPhase"));return;}
    Promise.all([fetch(`/api/tournaments/${tournamentId}`,{cache:"no-store",signal:controller.signal}),fetch(base,{cache:"no-store",signal:controller.signal})]).then(async([metaResponse,response])=>{
      const meta=await metaResponse.json();const state=await response.json();
      if(!metaResponse.ok||!response.ok)throw new Error(t("arenaPhases.error"));
      if(state.format==="champion_8"&&phase==="best8")throw new Error(t("arenaPhases.invalidPhase"));
      if(requestedPlayerId!=null&&!state.registrations.some((r:Registration)=>r.phase===phase&&r.eligible&&r.player_id===requestedPlayerId))throw new Error(t("arenaPhases.playerNotQualified"));
      setTournament(meta);setData(state);setPlayerId(requestedPlayerId??state.registrations.find((r:Registration)=>r.phase===phase&&r.eligible)?.player_id??null);
    }).catch(e=>{if(e.name!=="AbortError")setError(e.message);});return()=>controller.abort();
  },[base,phase,tournamentId,requestedPlayerId,t]);
  useEffect(()=>{const warn=(event:BeforeUnloadEvent)=>{if(dirty){event.preventDefault();event.returnValue="";}};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);
  const discard=()=>!dirty||window.confirm(t("arenaPhases.discard"));
  async function analyze(files:{file:File;preCropped:boolean}[]){
    if(!player||!data)return;setBusy("analysis");setError("");
    try{const target=data.format==="champion_8"
      ? {format:"champion_8" as const,tournamentId,playerId:player.id}
      : {format:"full_64" as const,tournamentId,seedNumber:player.seed_number!};
      setTeams(await analyzeRegistrationDecks(target,files));setDirty(true);
    }catch(e){setError(e instanceof Error?e.message:t("arenaPhases.error"));}finally{setBusy("");}
  }
  async function save(){
    if(!entry||!window.confirm(t(phase==="best8"?"arenaPhases.confirmBest8":data?.format==="champion_8"?"arenaPhases.confirmFinal8":"arenaPhases.confirmFinal64")))return;setBusy("teams");setError("");
    try{const next=await saveRegistrationDecks(`${base}/players/${entry.player_id}/${phase}`,"PUT",teams,{qualification:entry.qualification,revision_id:entry.revision_id},fetch,t);setData(next);setEditing(false);setDirty(false);setHistory([]);if(!await refreshCharacters())setError(t("arenaPhases.error"));
    }catch(e){setError(e instanceof Error?e.message:t("arenaPhases.error"));}finally{setBusy("");}
  }
  async function loadHistory(){try{const response=await fetch(base+"/history",{cache:"no-store"});if(!response.ok)throw new Error(t("arenaPhases.error"));setHistory((await response.json()).registrations);}catch(e){setError(e instanceof Error?e.message:t("arenaPhases.error"));}}
  return <main className="mx-auto max-w-7xl space-y-8 p-4 pb-32 md:p-8">
    <div className="flex flex-wrap items-center gap-4"><Link href={back} onClick={event=>{if(!discard())event.preventDefault();}} className="rounded-full bg-white/5 p-2 text-slate-400" aria-label={t("arenaPhases.backToBracket")}><ChevronLeft size={24}/></Link><div><h1 className="text-2xl font-black text-slate-100 md:text-3xl">{t(`arenaPhases.${registrationStage(phase,data?.format) ?? "unknown"}`)}</h1><p className="text-sm text-slate-400">{tournament?.name}</p></div></div>
    {tournament?.publication_status==="published"&&<p role="alert" className="text-amber-300">{t("arenaPhases.published")}</p>}
    {error&&<p role="alert" className="rounded-xl bg-red-950/50 p-3 text-red-300">{error}</p>}
    {!data||isLoading?(error?null:<p>{t("arenaPhases.loading")}</p>):<section className="rounded-3xl bg-slate-900/80 p-6 shadow-2xl ring-1 ring-white/10">
      <h2 className="mb-4 text-2xl font-black text-slate-200">{t("arenaPhases.registrations")}: {t(`arenaPhases.${registrationStage(phase,data?.format) ?? "unknown"}`)}</h2><p className="mb-5 text-sm text-slate-400">{t("arenaPhases.emptyNotice")}</p>
      {!eligible.length?<p className="text-amber-300">{t("arenaPhases.noQualifiedPlayers")}</p>:<DeckRegistrationViewport>
        {requestedPlayerId==null&&<label className="mb-2 block text-sm font-medium text-slate-400">{t("arenaPhases.name")}<select value={playerId??""} disabled={Boolean(busy)} onChange={event=>{if(discard()){setPlayerId(Number(event.target.value));setEditing(false);setDirty(false);setError("");}}} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-800/50 px-4 py-3 text-slate-100">{eligible.map(r=><option key={r.player_id} value={r.player_id}>{privateNames.name(data.players.find(p=>p.id===r.player_id)??{id:r.player_id})} · {t(r.complete?"arenaPhases.complete":"arenaPhases.incomplete")}</option>)}</select></label>}
        {entry&&player&&<><DeckRegistrationViewer playerName={privateNames.name(player)} playerDetail={t(`arenaPhases.${registrationStage(phase,data?.format) ?? "unknown"}`)} playerIconUrl={player.icon_url} teams={entry.teams} characters={characters} canEdit={writable&&!editing&&entry.complete} onEditTeams={()=>{setTeams(entry.teams.length?structuredClone(entry.teams):blankTeams());setEditing(true);}} />
          {writable&&!editing&&!entry.complete&&<button onClick={()=>{setTeams(blankTeams());setEditing(true);}} className="my-5 w-full rounded-xl bg-blue-600 py-4 font-bold text-white">{t("arenaPhases.edit")}</button>}
          {editing&&<DeckRegistrationEditor key={`${playerId}:${phase}`} teams={teams} characters={characters} saved={entry.complete} saveLabel={t("arenaPhases.saveVersion")} disabled={!writable||Boolean(busy)} busy={busy} error={error} dirty={dirty} onTeamsChange={next=>{setTeams(next);setDirty(true);}} onAnalyze={analyze} onSave={save} onClose={()=>{setEditing(false);setDirty(false);}} />}
          {data.registrations.filter(r=>r.player_id===playerId&&r.phase!==phase&&r.teams.length).map(r=><details key={r.phase} className="mt-5 rounded-xl bg-white/5 p-4"><summary>{t(`arenaPhases.${registrationStage(r.phase,data?.format) ?? "unknown"}`)}</summary><DeckRegistrationViewer playerName={privateNames.name(player)} playerDetail={t(`arenaPhases.${registrationStage(r.phase,data?.format) ?? "unknown"}`)} teams={r.teams} characters={characters}/></details>)}
          <details className="mt-5 rounded-xl bg-white/5 p-4" onToggle={event=>{if(event.currentTarget.open)void loadHistory();}}><summary>{t("arenaPhases.history")}</summary>{history.filter(r=>r.player_id===playerId&&r.phase===phase).map(r=><details key={r.id}><summary>#{r.id} · {t(`arenaPhases.${registrationStage(r.phase,data?.format) ?? "unknown"}`)}</summary><DeckRegistrationViewer playerName={privateNames.name(player)} teams={r.teams} characters={characters}/></details>)}</details>
        </>}
      </DeckRegistrationViewport>}
      <Link href={back} onClick={event=>{if(!discard())event.preventDefault();}} className="mt-6 inline-block rounded-xl bg-slate-800 px-5 py-3 font-bold text-slate-200">{t("arenaPhases.backToBracket")}</Link>
    </section>}
  </main>;
}
