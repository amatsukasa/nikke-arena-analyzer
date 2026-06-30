"use client";

interface Character {
  id: number;
  name: string;
  is_template_available: boolean;
}

export default function TeamDisplay({ charIds, allCharacters }: { charIds: number[], allCharacters: Character[] }) {
  const displayChars = charIds.map(cid => allCharacters.find(c => c.id === cid)).filter(Boolean);
  return (
    <div className="flex space-x-2">
      {displayChars.map((c: any, i: number) => {
        if (c.id === 9999) {
          return (
            <div key={i} className="flex flex-col items-center space-y-1 opacity-50">
              <div className="w-10 h-10 rounded-lg bg-slate-800/50 ring-1 ring-white/5 overflow-hidden flex items-center justify-center">
                <div className="text-slate-600 text-xs">-</div>
              </div>
              <span className="text-[9px] text-slate-500 w-10 truncate text-center" title="空枠">空枠</span>
            </div>
          );
        }
        return (
          <div key={i} className="flex flex-col items-center space-y-1 group">
            <div className="w-10 h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 overflow-hidden flex items-center justify-center transition-all">
              {c?.is_template_available ? (
                <img src={`/api/char-icon/${c.id}.png`} loading="lazy" decoding="async" alt={c?.name || "不明"} className="w-full h-full object-cover" />
              ) : (
                <span className="text-[10px] text-slate-500 font-bold leading-tight text-center">{c?.name?.slice(0, 3) || "不明"}</span>
              )}
            </div>
            <span className="text-[9px] text-slate-400 w-10 truncate text-center" title={c?.name || "不明"}>{c?.name || "不明"}</span>
          </div>
        );
      })}
    </div>
  );
}
