"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, ChevronDown, Upload, X } from "lucide-react";
import CharacterSearchSelect from "./CharacterSearchSelect";
import AnalysisCharacterCrop from "./AnalysisCharacterCrop";
import { RegistrationTeam, validateRegistrationTeams } from "../lib/deckRegistration";
import { prepareAnalysisImage } from "../lib/deckImagePreparation";
import { COLLECTION_OPTIONS, collectionSelectClass } from "../lib/collectionPresentation";
import { useMobileRoundAccordion } from "../hooks/useMobileRoundAccordion";
import { getCharIconUrl } from "../utils/charIcon";

type ChampionTeam = RegistrationTeam;

export interface RegistrationCharacter { id: number; name: string; rarity: string; image_url?: string; icon_url?: string | null }
interface Props {
  teams: RegistrationTeam[];
  characters: RegistrationCharacter[];
  saved: boolean;
  disabled?: boolean;
  busy?: "" | "analysis" | "teams" | "icon" | "player";
  error?: string;
  dirty?: boolean;
  onTeamsChange: (teams: RegistrationTeam[]) => void;
  onAnalyze: (prepared: { file: File; preCropped: boolean }[]) => Promise<void>;
  onSave: () => Promise<void>;
  onClose: () => void;
}

export default function DeckRegistrationEditor({ teams, characters, saved, disabled, busy, error, dirty = false, onTeamsChange, onAnalyze, onSave, onClose }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [localError, setLocalError] = useState("");
  const { expandedRound: expanded, roundToggleRefs, toggleRound } = useMobileRoundAccordion(0);
  const input = useRef<HTMLInputElement>(null);
  const known = useMemo(() => new Set(characters.map(item => item.id)), [characters]);
  const issues = useMemo(() => validateRegistrationTeams(teams, known), [teams, known]);
  const byId = useMemo(() => new Map(characters.map(item => [item.id, item])), [characters]);
  useEffect(() => () => previews.forEach(URL.revokeObjectURL), [previews]);
  const clearSelectedImages = () => { previews.forEach(URL.revokeObjectURL); setFiles([]); setPreviews([]); };
  const selectFiles = (selected: File[]) => { previews.forEach(URL.revokeObjectURL); const next = selected.slice(0, 5); setFiles(next); setPreviews(next.map(URL.createObjectURL)); setLocalError(""); };
  const analyze = async () => { setLocalError(""); try { const prepared = await Promise.all(files.map(file => prepareAnalysisImage(file))); await onAnalyze(prepared); } catch (caught) { setLocalError(caught instanceof Error ? caught.message : "画像の準備または解析に失敗しました。"); } };
  const close = () => {
    if ((dirty || files.length > 0) && !window.confirm("未保存の変更を破棄しますか？")) return;
    clearSelectedImages(); setLocalError(""); onClose();
  };
  const updateCharacter = (teamIndex: number, characterIndex: number, id: number | null) => onTeamsChange(teams.map((team, ti) => ti === teamIndex ? {...team, characters: team.characters.map((character, ci) => {
    if (ci !== characterIndex) return character;
    const corrected = id != null && id !== 9999 && Boolean(character.template_source_url||character.template_source_data_url) && (Boolean(character.was_unrecognized) || character.original_predicted_id !== id);
    return {...character, id, collection_level:id===9999?null:(character.collection_level||"unknown"), add_to_templates:corrected};
  })} : team));
  const updateCollection = (teamIndex: number, characterIndex: number, collection_level: string) => onTeamsChange(teams.map((team, ti) => ti === teamIndex ? {...team, characters: team.characters.map((character, ci) => ci === characterIndex ? {...character, collection_level} : character)} : team));
  const move = (index: number, offset: number) => { const target=index+offset; if(target<0||target>=teams.length)return; const next=[...teams]; [next[index],next[target]]=[next[target],next[index]]; onTeamsChange(next.map((team,i)=>({...team,team_number:i+1}))); };
  return <div className="space-y-6">
    <section className="rounded-3xl bg-slate-900/80 p-6 ring-1 ring-white/10"><div className="flex items-center justify-between"><h3 className="text-xl font-bold text-white">編成画像 (最大5枚)</h3><button onClick={close} aria-label="閉じる"><X /></button></div><p className="mt-2 text-sm text-slate-400">画像を追加し、full_64と同じ白背景検出・事前切り抜き後に解析します。解析結果は自動保存されません。</p><div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">{previews.map((url,index)=><img key={url} src={url} alt={`選択画像${index+1}`} className="aspect-[9/16] w-full rounded-lg object-cover ring-1 ring-white/10" />)}</div><div className="mt-4 flex flex-wrap gap-3"><button onClick={()=>input.current?.click()} disabled={disabled||Boolean(busy)} className="rounded-xl border-2 border-dashed border-blue-500/50 bg-blue-500/10 px-5 py-3 font-bold text-blue-400"><Upload className="mr-2 inline" size={18}/>{files.length ? "画像を追加・選び直す" : "画像を選択"}</button><input ref={input} hidden multiple type="file" accept="image/jpeg,image/png,image/webp" onChange={event=>{selectFiles(Array.from(event.target.files||[]));event.currentTarget.value="";}}/><button onClick={()=>void analyze()} disabled={disabled||!files.length||Boolean(busy)} className="rounded-xl bg-blue-600 px-6 py-3 font-bold text-white disabled:bg-slate-800 disabled:text-slate-500">{busy==="analysis"?"AIが解析中...":"AIで編成を解析する"}</button></div>{(localError||error)&&<div role="alert" className="mt-4 rounded-xl bg-red-950/50 p-3 text-red-300">{localError||error}</div>}</section>
    {teams.length>0&&<section className="rounded-3xl bg-slate-900/80 p-6 ring-1 ring-white/10"><h3 className="mb-6 flex items-center gap-2 text-xl font-bold text-white"><CheckCircle2 className="text-emerald-400"/>解析結果（プレビュー）</h3><div className="space-y-3">{teams.map((team,ti)=><div key={team.team_number} className="rounded-lg border border-white/10 bg-slate-900/40 p-2 sm:border-0 sm:bg-transparent"><div className="flex items-center gap-2"><div className="flex shrink-0 flex-col items-center"><button onClick={()=>move(ti,-1)} disabled={disabled||ti===0} className="p-1 text-slate-500 disabled:opacity-20" title="一つ上へ移動">▲</button><div className="flex h-8 w-8 items-center justify-center rounded bg-slate-800 font-mono text-xs text-slate-500">R{ti+1}</div><button onClick={()=>move(ti,1)} disabled={disabled||ti===teams.length-1} className="p-1 text-slate-500 disabled:opacity-20" title="一つ下へ移動">▼</button></div><button ref={element=>{roundToggleRefs.current[ti]=element;}} onClick={()=>toggleRound(ti)} className="flex min-h-12 flex-1 scroll-mt-4 items-center justify-between rounded-md bg-slate-800/70 px-3 sm:hidden" aria-expanded={expanded===ti}><b>ラウンド {ti+1}</b><ChevronDown className={expanded===ti?"rotate-180":""}/></button><div className="hidden min-w-0 flex-1 grid-cols-5 gap-2 sm:grid">{team.characters.map((character,ci)=><CharacterCell key={ci} character={character} info={character.id?byId.get(character.id):undefined} characters={characters} disabled={disabled} onCharacter={id=>updateCharacter(ti,ci,id)} onCollection={value=>updateCollection(ti,ci,value)} id={`desktop-${ti}-${ci}`}/>)}</div></div>{expanded===ti&&<div className="mt-2 space-y-2 sm:hidden">{team.characters.map((character,ci)=><CharacterCell key={ci} mobile character={character} info={character.id?byId.get(character.id):undefined} characters={characters} disabled={disabled} onCharacter={id=>updateCharacter(ti,ci,id)} onCollection={value=>updateCollection(ti,ci,value)} id={`mobile-${ti}-${ci}`}/>)}</div>}</div>)}</div>{issues.length?<div role="alert" className="mt-5 rounded-xl bg-red-950/50 p-4 text-sm text-red-200"><b>保存前に修正してください</b><ul className="mt-2 list-disc pl-5">{issues.map((issue,index)=><li key={index}>{issue}</li>)}</ul></div>:<p className="mt-5 text-emerald-400">25枠を確認済みです。</p>} {!disabled&&<button onClick={()=>void onSave()} disabled={Boolean(busy)||Boolean(issues.length)} className="mt-5 w-full rounded-xl bg-emerald-500/20 py-4 font-bold text-emerald-400 disabled:opacity-40">{busy==="teams"?"保存中...":saved?"この内容で編成を上書き":"この内容で編成を登録"}</button>}</section>}
  </div>;
}

function CharacterCell({character,info,characters,disabled,onCharacter,onCollection,id,mobile=false}:{character:ChampionTeam["characters"][number];info?:RegistrationCharacter;characters:RegistrationCharacter[];disabled?:boolean;onCharacter:(id:number|null)=>void;onCollection:(value:string)=>void;id:string;mobile?:boolean}) { const empty=character.id===9999; const validId=character.id!=null&&!empty; const imageUrl=character.preview_image_data_url||character.image_url||(info?getCharIconUrl({...info,is_template_available:Boolean(info.image_url||info.icon_url)}):"")||null; const fallback=empty?"空き枠":validId?(info?.name||`ID:${character.id}`):"未判定"; return <div className={mobile?"flex w-full min-w-0 items-center gap-3 rounded-md bg-slate-950/50 p-2":"flex w-full min-w-0 flex-col items-center gap-2"}><AnalysisCharacterCrop imageUrl={imageUrl} alt={info?.name||"解析Character"} fallback={fallback} className={`${mobile?"h-12 w-12":"h-16 w-16"} rounded-lg`}/><div className="w-full min-w-0 flex-1"><p className="mb-1 truncate text-center text-xs text-slate-300">{empty?"空き枠":info?.name||"未判定"}</p><CharacterSearchSelect id={id} value={character.id} onChange={onCharacter} characters={characters} error={character.id==null} className="w-full min-w-0"/><select aria-label={`${id} コレクション`} disabled={disabled||empty} value={empty?"unknown":character.collection_level||"unknown"} onChange={event=>onCollection(event.target.value)} className={`mt-2 h-9 w-full min-w-0 rounded border-2 px-2 text-xs font-bold ${collectionSelectClass(character.collection_level)}`}>{empty?<option value="unknown">判定不要</option>:COLLECTION_OPTIONS.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></div></div>; }
