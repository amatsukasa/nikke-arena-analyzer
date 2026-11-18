"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "../../context/AuthContext";

type Master={id:number;title:string;game_start_date:string|null;display_order:number|null;has_match_data:boolean};
const blank={title:"",game_start_date:"",display_order:""};

export default function ChampionArenaMastersAdmin(){
  const {apiFetch}=useAuth(); const api=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
  const [items,setItems]=useState<Master[]>([]); const [editing,setEditing]=useState<number|null>(null); const [form,setForm]=useState(blank); const [error,setError]=useState("");
  const load=useCallback(async()=>{const response=await apiFetch(`${api}/api/admin/champion-arena-tournaments`,{cache:"no-store"});if(response.ok)setItems(await response.json());else setError("戦績用大会を取得できませんでした。");},[api,apiFetch]);
  useEffect(()=>{void load();},[load]);
  const submit=async(event:FormEvent)=>{event.preventDefault();setError("");const response=await apiFetch(`${api}/api/admin/champion-arena-tournaments${editing?`/${editing}`:""}`,{method:editing?"PUT":"POST",body:JSON.stringify({title:form.title,game_start_date:form.game_start_date||null,display_order:form.display_order===""?null:Number(form.display_order)})});if(!response.ok){setError("保存できませんでした。");return;}setEditing(null);setForm(blank);await load();};
  const edit=(item:Master)=>{setEditing(item.id);setForm({title:item.title,game_start_date:item.game_start_date??"",display_order:item.display_order==null?"":String(item.display_order)});};
  return <details className="mt-8 border-t border-slate-800 pt-8"><summary className="cursor-pointer text-lg font-bold">個別大会の開催順・開始日</summary><p className="mt-1 text-sm text-slate-400">対戦データのない過去大会も登録できます。</p>
    {error&&<p role="alert" className="mt-3 text-red-300">{error}</p>}
    {editing!==null&&<form onSubmit={submit} className="mt-4 grid gap-3 rounded-lg bg-slate-950 p-4 md:grid-cols-2">
      <label>個別大会の名称<input required value={form.title} onChange={e=>setForm({...form,title:e.target.value})} className="mt-1 w-full rounded bg-slate-900 p-2"/></label>
      <label>表示順<input type="number" value={form.display_order} onChange={e=>setForm({...form,display_order:e.target.value})} className="mt-1 w-full rounded bg-slate-900 p-2"/></label>
      <label>大会の開始日（任意）<input type="date" value={form.game_start_date} onChange={e=>setForm({...form,game_start_date:e.target.value})} className="mt-1 w-full rounded bg-slate-900 p-2"/></label>
      <p className="text-sm text-slate-400 md:col-span-2">3つのチャンアリ設定は上の大会タイトル新規作成・編集で管理します。</p>
      <div className="flex gap-2"><button className="rounded bg-indigo-600 px-4 py-2">{editing?"更新":"登録"}</button>{editing&&<button type="button" onClick={()=>{setEditing(null);setForm(blank);}} className="rounded bg-slate-700 px-4 py-2">キャンセル</button>}</div>
    </form>}
    <div className="mt-4 space-y-2">{items.map(item=><div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-800 p-3"><span><b>#{item.id} {item.title}</b> / 順序 {item.display_order??"未設定"} / {item.has_match_data?"対戦データあり":"マスタのみ"}</span><button onClick={()=>edit(item)} className="rounded bg-slate-700 px-3 py-1">編集</button></div>)}</div>
  </details>;
}
