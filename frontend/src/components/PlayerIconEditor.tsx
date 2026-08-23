"use client";

import { useEffect, useRef, useState } from "react";
import Cropper, { Area } from "react-easy-crop";
import { Check, ImagePlus, Scissors, Trash2, X, ZoomIn } from "lucide-react";

async function cropImage(source: string, area: Area): Promise<Blob> {
  const image = new Image();
  image.src = source;
  await new Promise<void>((resolve, reject) => { image.onload = () => resolve(); image.onerror = reject; });
  const canvas = document.createElement("canvas");
  canvas.width = area.width; canvas.height = area.height;
  canvas.getContext("2d")?.drawImage(image, area.x, area.y, area.width, area.height, 0, 0, area.width, area.height);
  return await new Promise<Blob>((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("画像を切り抜けませんでした。")), "image/png"));
}

interface Props {
  iconUrl?: string | null;
  disabled?: boolean;
  busy?: boolean;
  onUpload: (file: File) => Promise<void>;
  onDelete?: () => Promise<void>;
  onSkip?: () => void;
}

export default function PlayerIconEditor({ iconUrl, disabled, busy, onUpload, onDelete, onSkip }: Props) {
  const [source, setSource] = useState<string | null>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [area, setArea] = useState<Area | null>(null);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const chooserRef = useRef<HTMLLabelElement>(null);
  useEffect(() => () => { if (source) URL.revokeObjectURL(source); }, [source]);
  useEffect(() => {
    if (!source) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !processing && !busy) cancel();
      if (event.key === "Tab" && dialogRef.current) {
        const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex="-1"])'));
        if (!focusable.length) return;
        const first=focusable[0], last=focusable[focusable.length-1];
        if (event.shiftKey && document.activeElement===first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement===last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    dialogRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [source, processing, busy]);
  const resetTemporaryState = () => { if (source) URL.revokeObjectURL(source); setSource(null); setArea(null); setZoom(1); setCrop({ x: 0, y: 0 }); setError(""); window.requestAnimationFrame(() => returnFocusRef.current?.focus()); };
  const cancel = () => { if (processing || busy) return; resetTemporaryState(); };
  const choose = (file?: File) => { if (!file) return; returnFocusRef.current = chooserRef.current; if (source) URL.revokeObjectURL(source); setSource(URL.createObjectURL(file)); setZoom(1); setCrop({ x: 0, y: 0 }); setArea(null); setError(""); };
  const confirm = async () => {
    if (!source || !area || processing || busy) return;
    setProcessing(true);
    setError("");
    try {
      const blob = await cropImage(source, area);
      await onUpload(new File([blob], "avatar.png", { type: "image/png" }));
      resetTemporaryState();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Player画像を保存できませんでした。");
    } finally {
      setProcessing(false);
    }
  };
  return <section className="rounded-xl bg-white/5 p-4">
    <h3 className="mb-3 font-bold text-white">Player画像（任意）</h3>
    <div className="flex flex-wrap items-center gap-3">
      {iconUrl ? <img src={iconUrl} alt="現在のPlayer画像" className="h-20 w-20 rounded-full border-2 border-blue-500/40 object-cover" /> : <div className="flex h-20 w-20 items-center justify-center rounded-full bg-slate-800 text-slate-500">未登録</div>}
      {!disabled && <><label ref={chooserRef} tabIndex={0} className="cursor-pointer rounded-xl bg-slate-800 px-4 py-3 font-bold text-slate-200 hover:bg-slate-700"><ImagePlus className="mr-2 inline" size={18} />画像を選択<input className="hidden" type="file" accept="image/jpeg,image/png,image/webp" onChange={event => { choose(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label>{iconUrl && onDelete && <button type="button" disabled={busy||processing} onClick={() => void onDelete()} className="rounded-xl bg-red-950 px-4 py-3 font-bold text-red-300"><Trash2 className="mr-2 inline" size={18} />削除</button>}{onSkip&&<button type="button" onClick={onSkip} className="rounded-xl border border-slate-700 px-4 py-3 font-bold text-slate-300">次へ（編成登録）</button>}</>}
    </div>
    {source && <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/90 p-4 backdrop-blur-md" onMouseDown={event=>{if(event.target===event.currentTarget)cancel();}}><div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="プロフィール画像の編集" className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-3xl bg-slate-900 shadow-2xl ring-1 ring-white/10"><div className="flex items-center justify-between border-b border-white/5 p-6"><h3 className="flex items-center gap-2 text-xl font-black text-white"><Scissors className="text-blue-400" />プロフィール画像の編集</h3><button onClick={cancel} disabled={processing||busy} aria-label="キャンセル"><X /></button></div><div className="relative min-h-[400px] flex-1 bg-black"><Cropper image={source} crop={crop} zoom={zoom} maxZoom={10} aspect={1} cropShape="round" showGrid={false} onCropChange={setCrop} onZoomChange={setZoom} onCropComplete={(_, pixels) => setArea(pixels)} /></div><div className="space-y-5 p-6">{error&&<div role="alert" className="rounded-xl bg-red-950/50 p-3 text-red-300">{error}</div>}<div className="flex justify-between text-sm text-slate-400"><span><ZoomIn className="mr-1 inline" size={15} />ズーム調節</span><b className="text-blue-400">{Math.round(zoom * 100)}%</b></div><div className="grid grid-cols-3 gap-2">{[[1,"小 (1倍)"],[6,"中 (6倍)"],[10,"大 (10倍)"]].map(([value,label]) => <button key={value} disabled={processing||busy} onClick={() => setZoom(Number(value))} className={`rounded-lg px-3 py-2 text-sm font-bold ${zoom === value ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-400"}`}>{label}</button>)}</div><div className="flex gap-4"><button onClick={cancel} disabled={processing||busy} className="flex-1 rounded-xl bg-slate-800 py-3 font-bold text-slate-300 disabled:opacity-50">キャンセル</button><button onClick={() => void confirm()} disabled={processing||busy||!area} className="flex-1 rounded-xl bg-blue-600 py-3 font-bold text-white disabled:opacity-50"><Check className="mr-2 inline" size={18} />{processing||busy?"処理中...":"決定してアップロード"}</button></div></div></div></div>}
  </section>;
}
