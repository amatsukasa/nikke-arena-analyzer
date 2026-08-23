"use client";

import { User } from "lucide-react";

interface Props {
  name: string;
  eyebrow: string;
  iconUrl?: string | null;
  align?: "left" | "right" | "center";
  scale?: number;
  winner?: boolean;
  selected?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

export default function TournamentPlayerPill({ name, eyebrow, iconUrl, align="left", scale=1, winner=false, selected=false, disabled=false, onClick }: Props) {
  return <button type="button" aria-pressed={selected} disabled={disabled} onClick={event=>{event.stopPropagation();onClick?.();}} className={`flex items-center gap-2 rounded-full border bg-slate-900/90 p-1.5 backdrop-blur-md transition-all ${disabled?"cursor-default":"cursor-pointer hover:border-blue-400 hover:bg-slate-800"} ${winner?"relative z-30 border-amber-400 shadow-[0_0_15px_rgba(251,191,36,0.4)]":selected?"relative z-30 border-blue-400 shadow-[0_0_14px_rgba(96,165,250,0.45)]":"border-slate-600/50"} ${align==="right"?"flex-row-reverse":""}`} style={{transform:`scale(${scale})`}}>
    <span className={`relative flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 bg-slate-800 ${winner?"border-amber-400":"border-slate-700"}`}>{iconUrl?<img src={iconUrl} alt={`${name}のPlayer画像`} className="h-full w-full object-cover"/>:<User size={20} className="text-slate-600"/>}</span>
    <span className={`flex min-w-[80px] max-w-[100px] flex-col justify-center px-2 ${align==="right"?"items-end text-right":"items-start text-left"}`}><span className="text-[10px] font-bold tracking-wider text-slate-400">{eyebrow}</span><span className={`w-full truncate text-xs font-black ${winner?"text-amber-400":"text-slate-200"}`}>{name}</span></span>
  </button>;
}
