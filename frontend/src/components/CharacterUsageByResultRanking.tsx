"use client";

import { useState } from "react";
import { Users } from "lucide-react";
import { getCharIconUrl } from "@/utils/charIcon";

const RESULT_FILTERS = [
  { key: "all", label: "全体" },
  { key: "best16", label: "ベスト16以上" },
  { key: "best8", label: "ベスト8以上" },
  { key: "best4", label: "ベスト4以上" },
  { key: "runner_up", label: "準優勝以上" },
  { key: "champion", label: "優勝" },
] as const;

type ResultFilterKey = (typeof RESULT_FILTERS)[number]["key"];

type Props = {
  stats: any;
  allCharacters: any[];
  onSelectCharacter: (characterId: number) => void;
};

export default function CharacterUsageByResultRanking({
  stats,
  allCharacters,
  onSelectCharacter,
}: Props) {
  const [resultFilter, setResultFilter] = useState<ResultFilterKey>("best8");
  const selected = stats?.character_usage_by_result?.[resultFilter];
  const denominator = selected?.denominator ?? 0;
  const characters = selected?.characters ?? [];
  const label = selected?.label
    ?? RESULT_FILTERS.find((filter) => filter.key === resultFilter)?.label
    ?? "";

  return (
    <section>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="flex items-center space-x-2 text-xl font-bold text-white">
            <Users className="text-blue-400" />
            <span>キャラクター採用率ランキング</span>
          </h2>
          <p className="mt-2 text-sm font-medium text-slate-300">
            対象：{label} {denominator}人
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <span className="whitespace-nowrap">最終成績</span>
          <select
            value={resultFilter}
            onChange={(event) => setResultFilter(event.target.value as ResultFilterKey)}
            className="rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-white outline-none focus:border-blue-500"
          >
            {RESULT_FILTERS.map((filter) => (
              <option key={filter.key} value={filter.key}>
                {filter.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="overflow-x-auto rounded-xl bg-slate-900/50 shadow-2xl ring-1 ring-white/10">
        <table className="w-full min-w-[560px] border-collapse text-left">
          <thead>
            <tr className="border-b border-white/10 bg-slate-800/80 text-sm text-slate-400">
              <th className="w-16 p-4 text-center font-medium">順位</th>
              <th className="w-24 p-4 text-center font-medium">採用数</th>
              <th className="w-24 p-4 text-center font-medium">採用率</th>
              <th className="p-4 font-medium">キャラクター名</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {characters.map((entry: any, index: number) => {
              const characterId = entry.character_id ?? entry.id;
              const character = allCharacters.find((item) => item.id === characterId) ?? entry;
              const previous = characters[index - 1];
              const rank = previous && previous.count === entry.count
                ? characters.findIndex((item: any) => item.count === entry.count) + 1
                : index + 1;

              return (
                <tr key={characterId} className="transition-colors hover:bg-white/5">
                  <td className="p-4 text-center">
                    <span className={`inline-flex h-8 w-8 items-center justify-center rounded-full font-black ${
                      rank === 1 ? "bg-yellow-500/20 text-yellow-500 ring-1 ring-yellow-500/50" :
                      rank === 2 ? "bg-slate-300/20 text-slate-300 ring-1 ring-slate-300/50" :
                      rank === 3 ? "bg-amber-600/20 text-amber-500 ring-1 ring-amber-600/50" :
                      "text-slate-500"
                    }`}>
                      {rank}
                    </span>
                  </td>
                  <td className="p-4 text-center font-bold text-slate-200">{entry.count}人</td>
                  <td className="p-4 text-center font-bold text-blue-300">
                    {Number(entry.usage_rate ?? 0).toFixed(1)}%
                  </td>
                  <td className="p-4">
                    <button
                      type="button"
                      onClick={() => onSelectCharacter(characterId)}
                      className="flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-slate-700"
                    >
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-md bg-slate-700 ring-1 ring-white/10">
                        {getCharIconUrl(character) ? (
                          <img
                            src={getCharIconUrl(character)}
                            loading="lazy"
                            decoding="async"
                            alt={character.name}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <span className="text-[8px] font-bold text-slate-500">
                            {character.name?.slice(0, 2)}
                          </span>
                        )}
                      </span>
                      <span className="font-bold text-slate-200">{character.name}</span>
                    </button>
                  </td>
                </tr>
              );
            })}
            {characters.length === 0 && (
              <tr>
                <td colSpan={4} className="p-8 text-center text-slate-500">
                  対象データがありません
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
