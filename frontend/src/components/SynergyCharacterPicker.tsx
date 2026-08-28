"use client";

import { useEffect, useRef, useState } from "react";
import { getCharIconUrl } from "@/utils/charIcon";
import { CharacterUsageCount, mapAndSortSynergyCharacters, shouldResetSynergySelection, SynergyCharacter, transitionSynergySelection } from "@/lib/synergyCharacters";

type UsageState = "loading" | "ready" | "error";

export function useResetSynergyOnAnalysisChange(analysisKey: string | null, reset: () => void) {
  const previousKey = useRef<string | null>(null);
  const resetRef = useRef(reset);
  resetRef.current = reset;

  useEffect(() => {
    if (!analysisKey) return;
    if (shouldResetSynergySelection(previousKey.current, analysisKey)) {
      resetRef.current();
    }
    previousKey.current = analysisKey;
  }, [analysisKey]);
}

export default function SynergyCharacterPicker({
  characters,
  characterUsage,
  usageState,
  includedIds,
  excludedIds,
  onChange,
}: {
  characters: SynergyCharacter[];
  characterUsage: CharacterUsageCount[];
  usageState: UsageState;
  includedIds: number[];
  excludedIds: number[];
  onChange: (selection: { includedIds: number[]; excludedIds: number[] }) => void;
}) {
  const [notice, setNotice] = useState("");
  const options = usageState === "ready"
    ? mapAndSortSynergyCharacters(characters, characterUsage)
    : characters.map((character) => ({ character, count: 0, unavailable: false }));

  return (
    <div className="flex flex-wrap gap-2">
      {options.map(({ character, unavailable }) => {
        const isIncluded = includedIds.includes(character.id);
        const isExcluded = excludedIds.includes(character.id);
        const unavailableReason = "選択した大会では採用実績がありません";
        const unavailableByState = usageState !== "ready";
        const disabled = unavailable || unavailableByState;
        const title = unavailable
          ? unavailableReason
          : usageState === "loading"
            ? "採用実績を読み込み中です"
            : usageState === "error"
              ? "採用実績を取得できませんでした"
              : character.name || "";

        return (
          <button
            type="button"
            key={character.id}
            disabled={disabled}
            data-state={unavailable ? "unavailable" : isIncluded ? "include" : isExcluded ? "exclude" : "none"}
            aria-label={unavailable
              ? `${character.name}、選択した大会では採用実績なし、選択不可`
              : isIncluded
                ? `${character.name}、検索対象`
                : isExcluded
                  ? `${character.name}、除外対象`
                  : character.name || ""}
            onClick={() => {
              if (disabled) return;
              const next = transitionSynergySelection(character.id, includedIds, excludedIds);
              onChange(next);
              setNotice(next.addedAsExclusionDueToLimit ? "検索対象は5人までのため、除外条件として追加しました" : "");
            }}
            className={`relative h-12 w-12 overflow-hidden rounded-lg transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 ${
              isIncluded
                ? "scale-110 ring-2 ring-emerald-500 shadow-lg"
                : isExcluded
                  ? "ring-2 ring-red-500 shadow-lg"
                : unavailable
                  ? "cursor-not-allowed opacity-35 grayscale ring-1 ring-white/10"
                  : usageState === "loading"
                    ? "cursor-wait opacity-70 ring-1 ring-white/10"
                    : usageState === "error"
                      ? "cursor-not-allowed opacity-70 ring-1 ring-white/10"
                    : "opacity-70 ring-1 ring-white/10 hover:opacity-100"
            }`}
            title={title}
          >
            {getCharIconUrl(character) ? (
              <img src={getCharIconUrl(character)} loading="lazy" decoding="async" alt={character.name || ""} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-slate-800 text-center text-[10px] font-bold leading-tight text-slate-400">
                {(character.name || "").slice(0, 4)}
              </div>
            )}
            {isIncluded && <div aria-hidden="true" className="absolute right-0 top-0 flex h-5 w-5 items-center justify-center rounded-bl-md bg-emerald-600 text-[11px] leading-none text-white">✅</div>}
            {isExcluded && <div aria-hidden="true" className="absolute right-0 top-0 flex h-5 w-5 items-center justify-center rounded-bl-md bg-red-600 text-[11px] leading-none text-white">✕</div>}
          </button>
        );
      })}
      <div className="w-full pt-1 text-xs text-slate-400">
        <span>タップするたびに切り替わります　</span>
        <span className="font-bold text-emerald-400">✅ 検索対象</span>
        <span>　</span>
        <span className="font-bold text-red-400">✖ 除外対象</span>
        {notice && <div role="status" className="mt-1 text-amber-300">{notice}</div>}
      </div>
    </div>
  );
}
