"use client";

import { useState } from "react";
import { Users } from "lucide-react";
import { getCharIconUrl } from "@/utils/charIcon";
import { useI18n } from "@/i18n/I18nProvider";

const RESULT_FILTERS = [
  { key: "all", label: "common.all" },
  { key: "best16", label: "result.best16" },
  { key: "best8", label: "result.best8" },
  { key: "best4", label: "result.semifinal" },
  { key: "runner_up", label: "result.runnerUp" },
  { key: "champion", label: "result.champion" },
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
  const { t } = useI18n();
  const [resultFilter, setResultFilter] = useState<ResultFilterKey>("best8");
  const selected = stats?.character_usage_by_result?.[resultFilter];
  const denominator = selected?.denominator ?? 0;
  const characters = selected?.characters ?? [];
  const label = t(RESULT_FILTERS.find((filter) => filter.key === resultFilter)?.label ?? "common.all");
  const groups: Array<{
    count: number;
    usageRate: number;
    rank: number;
    characters: any[];
  }> = [];

  characters.forEach((entry: any, index: number) => {
    const count = Number(entry.count ?? 0);
    const usageRate = Number(entry.usage_rate ?? 0);
    const lastGroup = groups[groups.length - 1];
    if (lastGroup && lastGroup.count === count && lastGroup.usageRate === usageRate) {
      lastGroup.characters.push(entry);
      return;
    }
    groups.push({
      count,
      usageRate,
      rank: index + 1,
      characters: [entry],
    });
  });

  return (
    <section>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="flex items-center space-x-2 text-xl font-bold text-white">
            <Users className="text-blue-400" />
            <span>{t('stats.characterPickRanking')}</span>
          </h2>
          <p className="mt-2 text-sm font-medium text-slate-300">
            {t('stats.targetByResult', { result: label, count: denominator })}
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <span className="whitespace-nowrap">{t('stats.finalResult')}</span>
          <select
            value={resultFilter}
            onChange={(event) => setResultFilter(event.target.value as ResultFilterKey)}
            className="rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-white outline-none focus:border-blue-500"
          >
            {RESULT_FILTERS.map((filter) => (
              <option key={filter.key} value={filter.key}>{t(filter.label)}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="overflow-hidden rounded-xl bg-slate-900/50 shadow-2xl ring-1 ring-white/10">
        <div className="hidden grid-cols-[4rem_7rem_8rem_minmax(0,1fr)] border-b border-white/10 bg-slate-800/80 text-sm text-slate-400 md:grid">
          <div className="p-4 text-center font-medium">{t('stats.rank')}</div>
          <div className="p-4 text-center font-medium">{t('stats.usageCount')}</div>
          <div className="p-4 text-center font-medium">{t('stats.adoptionRate')}</div>
          <div className="p-4 font-medium">{t('stats.character')}</div>
        </div>

        <div className="divide-y divide-white/5">
          {groups.map((group) => (
            <div
              key={`${group.rank}-${group.count}-${group.usageRate}`}
              className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-3 p-3 transition-colors hover:bg-white/5 sm:p-4 md:grid-cols-[4rem_7rem_8rem_minmax(0,1fr)] md:items-start md:gap-0 md:p-0"
            >
              <div className="row-span-2 flex items-center justify-center md:row-span-1 md:p-4">
                <span className={`inline-flex h-8 w-8 items-center justify-center rounded-full font-black ${
                  group.rank === 1 ? "bg-yellow-500/20 text-yellow-500 ring-1 ring-yellow-500/50" :
                  group.rank === 2 ? "bg-slate-300/20 text-slate-300 ring-1 ring-slate-300/50" :
                  group.rank === 3 ? "bg-amber-600/20 text-amber-500 ring-1 ring-amber-600/50" :
                  "text-slate-500"
                }`}>
                  {group.rank}
                </span>
              </div>

              <div className="flex items-center gap-2 text-sm md:contents">
                <span className="font-bold text-slate-200 md:p-4 md:text-center">{t('stats.countTimes', { count: group.count })}</span>
                <span className="text-slate-600 md:hidden">・</span>
                <span className="font-bold text-blue-300 md:p-4 md:text-center">{group.usageRate.toFixed(1)}%</span>
              </div>

              <div className="col-start-2 flex min-w-0 flex-wrap gap-2 md:col-start-auto md:p-3">
                {group.characters.map((entry: any) => {
                  const characterId = entry.character_id ?? entry.id;
                  const character = allCharacters.find((item) => item.id === characterId) ?? entry;
                  return (
                    <button
                      key={characterId}
                      type="button"
                      onClick={() => onSelectCharacter(characterId)}
                      className="flex min-w-0 items-center gap-2 rounded-lg bg-slate-800/70 px-2 py-1.5 ring-1 ring-white/10 transition-colors hover:bg-slate-700 hover:ring-blue-500/50"
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
                          <span className="text-[8px] font-bold text-slate-500">{character.name?.slice(0, 2)}</span>
                        )}
                      </span>
                      <span className="max-w-28 truncate text-sm font-bold text-slate-200 sm:max-w-none">{character.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          {groups.length === 0 && (
            <div className="p-8 text-center text-slate-500">{t('common.noData')}</div>
          )}
        </div>
      </div>
    </section>
  );
}
