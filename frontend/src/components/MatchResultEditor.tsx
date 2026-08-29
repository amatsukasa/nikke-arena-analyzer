"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Upload, User } from "lucide-react";
import TeamDisplay from "./TeamDisplay";
import { MatchEditorPlayer, MatchEditorResult, MatchSide, majoritySide, validateMatchEditorResult } from "../lib/matchRegistration";

interface Team { team_number:number; characters:Array<{id:number|null;collection_level:string|null}> }
interface Character { id:number; name:string; is_template_available?:boolean; icon_url?:string }
interface Props {
  attacker: MatchEditorPlayer; defender: MatchEditorPlayer;
  attackerTeams?: Team[]; defenderTeams?: Team[]; characters?: Character[];
  initialResult?: MatchEditorResult | null; existing?: boolean; disabled?: boolean; busy?: boolean; error?: string;
  dependencyWarning?: string;
  onAnalyze: (file: File) => Promise<MatchEditorResult>;
  onSave: (result: MatchEditorResult) => Promise<void>;
  onClose?: () => void;
  onDirtyChange?: (dirty:boolean) => void;
}

export default function MatchResultEditor({attacker,defender,attackerTeams=[],defenderTeams=[],characters=[],initialResult=null,existing=false,disabled=false,busy=false,error="",dependencyWarning,onAnalyze,onSave,onClose,onDirtyChange}:Props){
  const [file,setFile]=useState<File|null>(null); const [preview,setPreview]=useState<string|null>(null); const [result,setResult]=useState<MatchEditorResult|null>(initialResult); const [dirty,setDirty]=useState(false); const inputRef=useRef<HTMLInputElement>(null);
  useEffect(()=>setResult(initialResult),[initialResult]);
  useEffect(()=>onDirtyChange?.(dirty),[dirty,onDirtyChange]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);
  const choose=(next:File|null)=>{if(preview)URL.revokeObjectURL(preview);setFile(next);setPreview(next?URL.createObjectURL(next):null);setDirty(Boolean(next)||Boolean(result));};
  const close=()=>{if(busy)return;if(dirty&&!window.confirm("未保存の勝敗修正を破棄しますか？"))return;onClose?.();};
  const updateRound=(number:number,winner:MatchSide|null)=>{setResult(current=>current?{...current,issues:[],rounds:current.rounds.map(round=>round.roundNumber===number?{...round,winner}:round)}:current);setDirty(true);};
  const issues=validateMatchEditorResult(result); const winner=result?majoritySide(result.rounds):null;
  const teams=(label:string,items:Team[])=><div className="space-y-1"><p className="text-xs font-bold text-slate-400">{label}の5部隊</p>{items.length?[...items].sort((a,b)=>a.team_number-b.team_number).map(team=><div key={team.team_number} className="flex items-center gap-2 rounded-lg bg-slate-950/50 p-2"><span className="w-7 text-xs font-black text-slate-500">R{team.team_number}</span><TeamDisplay charIds={team.characters.map(c=>c.id??9999)} collectionLevels={team.characters.map(c=>c.collection_level)} allCharacters={characters as any}/></div>):<p className="text-xs text-slate-500">編成情報を表示できません。</p>}</div>;
  const player=(side:"攻撃側（左）"|"防衛側（右）",p:MatchEditorPlayer)=><div className="flex items-center gap-3 rounded-xl bg-slate-800/70 p-3"><div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-full bg-slate-950">{p.iconUrl?<img src={p.iconUrl} alt="" className="h-full w-full object-cover"/>:<User size={18}/>}</div><div><p className="text-xs font-bold text-slate-400">{side}</p><b>{p.name}</b>{p.detail&&<p className="text-xs text-slate-400">{p.detail}</p>}</div></div>;
  return <section className="space-y-5" data-match-result-editor>
    <div className="grid gap-3 sm:grid-cols-2">{player("攻撃側（左）",attacker)}{player("防衛側（右）",defender)}</div>
    <div className="grid gap-4 lg:grid-cols-2">{teams(attacker.name,attackerTeams)}{teams(defender.name,defenderTeams)}</div>
    {dependencyWarning&&<div className="rounded-xl border border-amber-700/50 bg-amber-950/30 p-3 text-sm text-amber-200">{dependencyWarning}</div>}
    {error&&<div role="alert" className="rounded-xl bg-red-950/50 p-3 text-red-300">{error}</div>}
    {!disabled&&<><div className="rounded-xl border border-white/10 bg-slate-800/50 p-4">{preview?<div className="mx-auto max-w-48"><img src={preview} alt="選択したリザルト画像" className="max-h-72 w-full rounded-lg object-contain"/><button disabled={busy} onClick={()=>choose(null)} className="mt-2 w-full rounded-lg bg-slate-700 py-2">画像を選び直す</button></div>:<button onClick={()=>inputRef.current?.click()} className="flex w-full flex-col items-center rounded-xl border-2 border-dashed border-emerald-500/50 py-10 text-emerald-400"><Upload/><b>リザルト画像を選択</b><span className="text-xs">1枚</span></button>}<input ref={inputRef} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>choose(e.target.files?.[0]??null)}/></div><button disabled={!file||busy} onClick={async()=>{if(!file)return;try{const analyzed=await onAnalyze(file);setResult(analyzed);setDirty(true);}catch{/* Parent displays the API error. */}}} className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 py-4 font-bold disabled:opacity-40">{busy?<><Loader2 className="animate-spin"/>解析中...</>:"AIで勝敗を解析する"}</button></>}
    {result&&<div className="space-y-2 rounded-xl bg-emerald-950/20 p-4" data-analysis-complete={issues.length===0&&Boolean(winner)}><h3 className="font-black">解析結果（プレビュー）</h3>{[...result.rounds].sort((a,b)=>a.roundNumber-b.roundNumber).map(round=><div key={round.roundNumber} className="grid grid-cols-[2rem_3rem_1fr_3rem] items-center gap-2 rounded-lg bg-slate-800/70 p-3 text-center sm:grid-cols-[3rem_1fr_1.5fr_1fr]"><b>R{round.roundNumber}</b><span className={round.winner==="left"?"font-black text-blue-400":"text-slate-500"}>{round.winner==null?"-":round.winner==="left"?"WIN":"LOSE"}</span>{disabled?<span className="text-xs text-slate-300">{round.winner==="left"?`${attacker.name}（左）の勝利`:round.winner==="right"?`${defender.name}（右）の勝利`:"未判定"}</span>:<select aria-label={`ラウンド${round.roundNumber}の勝者`} disabled={busy} value={round.winner??""} onChange={e=>updateRound(round.roundNumber,e.target.value==="left"||e.target.value==="right"?e.target.value:null)} className="min-w-0 rounded-lg bg-slate-950 p-2 text-xs"><option value="">未判定</option><option value="left">{attacker.name}（左）の勝利</option><option value="right">{defender.name}（右）の勝利</option></select>}<span className={round.winner==="right"?"font-black text-red-400":"text-slate-500"}>{round.winner==null?"-":round.winner==="right"?"WIN":"LOSE"}</span></div>)}<p className="pt-2 text-center text-lg font-black text-emerald-300">{winner?`${winner==="left"?attacker.name:defender.name}の勝利`:"勝者未確定"}</p>{issues.length>0&&<ul className="text-sm text-red-300">{issues.map(issue=><li key={issue}>・{issue}</li>)}</ul>}{!disabled&&<button disabled={busy||issues.length>0||!winner} onClick={async()=>{if(existing&&!window.confirm("登録済みの勝敗を上書きしますか？"))return;if(!existing&&!window.confirm("この内容で勝敗を登録しますか？"))return;try{await onSave(result);setDirty(false);}catch{/* Parent displays the API error and keeps edits. */}}} className="w-full rounded-xl bg-blue-600 py-4 font-bold disabled:opacity-40">この内容で勝敗を登録する</button>}</div>}
    {onClose&&<button disabled={busy} onClick={close} className="w-full rounded-xl bg-slate-800 py-3">勝敗登録を閉じる</button>}
  </section>;
}
