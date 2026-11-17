"use client";
import {useEffect,useState} from "react";
import {useI18n} from "@/i18n/I18nProvider";
export default function PrivatePlayerNameEditor({tournamentId,playerId,seedNumber,value,onSaved}:{tournamentId:number;playerId?:number;seedNumber?:number;value:string|null;onSaved:()=>Promise<void>}){
 const {t}=useI18n();const [name,setName]=useState(value??"");const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [saved,setSaved]=useState(false);
 useEffect(()=>{setName(value??"");setError("");setSaved(false);},[value,playerId,seedNumber]);
 async function save(){setBusy(true);setError("");setSaved(false);try{
  const response=await fetch(`/api/tournaments/${tournamentId}/private-player-names`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({...playerId?{player_id:playerId}:{seed_number:seedNumber},private_name:name.trim()||null})});
  if(!response.ok)throw new Error(t("privatePlayerName.error"));await onSaved();setSaved(true);
 }catch(e){setError(e instanceof Error?e.message:t("privatePlayerName.error"));}finally{setBusy(false);}}
 return <section className="space-y-2 rounded-xl bg-white/5 p-4"><label className="block text-sm text-slate-300">{t("privatePlayerName.label")}<input maxLength={50} value={name} disabled={busy} onChange={e=>{setName(e.target.value);setSaved(false);}} placeholder={t("privatePlayerName.unset")} className="mt-2 w-full rounded-lg bg-slate-800 px-3 py-2"/></label><p className="text-xs text-slate-400">{t("privatePlayerName.notice")}</p><button type="button" onClick={()=>void save()} disabled={busy} className="rounded-lg bg-blue-600 px-4 py-2 disabled:opacity-40">{t("privatePlayerName.save")}</button>{saved&&<p role="status" className="text-emerald-300">{t("privatePlayerName.saved")}</p>}{error&&<p role="alert" className="text-red-300">{error}</p>}</section>;
}
