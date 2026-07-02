"use client";

import { getCharIconUrl } from "@/utils/charIcon";

interface Character {
  id: number;
  name: string;
  is_template_available: boolean;
  template_filename?: string;
  icon_url?: string;
}

export default function TeamDisplay({
  charIds,
  allCharacters = []
}: {
  charIds: number[];
  allCharacters?: Character[];
}) {
  const displayChars = charIds.map(cid => {
    return allCharacters.find(c => c.id === cid) || {
      id: cid,
      name: String(cid),
      is_template_available: cid !== 9999,
    };
  });
  return (
    <div className="flex space-x-1 sm:space-x-2">
      {displayChars.map((c: any, i: number) => {
        if (c.id === 9999) {
          return (
            <div key={i} className="flex flex-col items-center space-y-1 opacity-50">
              <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-slate-800/50 ring-1 ring-white/5 overflow-hidden flex items-center justify-center">
                <div className="text-slate-600 text-xs">-</div>
              </div>
              <span className="text-[8px] sm:text-[9px] text-slate-500 w-9 sm:w-10 truncate text-center" title="空枠">空枠</span>
            </div>
          );
        }
        return (
          <div key={i} className="flex flex-col items-center space-y-1 group">
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 overflow-hidden flex items-center justify-center transition-all">
              {getCharIconUrl(c) ? (
                <img src={getCharIconUrl(c)} loading="lazy" decoding="async" alt={c?.name || "不明"} className="w-full h-full object-cover" />
              ) : (
                <span className="text-[10px] text-slate-500 font-bold leading-tight text-center">{c?.name?.slice(0, 3) || "不明"}</span>
              )}
            </div>
            <span className="text-[8px] sm:text-[9px] text-slate-400 w-9 sm:w-10 truncate text-center" title={c?.name || "不明"}>{c?.name || "不明"}</span>
          </div>
        );
      })}
    </div>
  );
}
