"use client";

import { useState, type ReactNode } from "react";
import TeamDisplay from "@/components/TeamDisplay";
import { useI18n } from "@/i18n/I18nProvider";
import {
  summaryStageLabel, type Adoption, type AdoptionChange, type StageAdoption, type StageGrowth,
  type SummaryStage, type SummaryStatistics, type WeaponMetric, type WeaponTransition,
} from "@/lib/seasonSummary";

type Character = { id: number; name: string; is_template_available: boolean; icon_url?: string };

const metrics = ["slots", "commanders"] as const;
const burstLabels = { "1": "Ⅰ", "2": "Ⅱ", "3": "Ⅲ" } as const;
const wrap = "min-w-0 rounded-2xl border border-white/10 bg-slate-950/60 px-4 sm:px-6";
const disclosure = "min-h-11 cursor-pointer py-3 font-bold";
const selector = "min-h-11 rounded-lg border border-white/15 px-3 text-sm text-slate-300 hover:bg-white/10 aria-pressed:border-sky-500 aria-pressed:bg-sky-900 aria-pressed:text-white";
const table = "w-full table-fixed text-left text-xs sm:text-sm";
const cell = "border-b border-white/10 px-1.5 py-2 first:pl-0 sm:px-3";
const namespace = "seasonAdoption.";

function Counts({ value }: { value: Adoption }) {
  const { locale } = useI18n();
  const number = new Intl.NumberFormat(locale);
  const percent = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 });
  if (value.rate === null) return <span className="text-slate-400">—</span>;
  return <span className="tabular-nums">
    <strong className="block text-sky-200">{percent.format(value.rate / 100)}</strong>
    <span className="text-slate-300">{number.format(value.count)} / {number.format(value.population)}</span>
  </span>;
}

function Change({ value }: { value: number | null }) {
  const { t, locale } = useI18n();
  if (value === null) return <span className="text-slate-400">—</span>;
  const text = new Intl.NumberFormat(locale, { maximumFractionDigits: 1, signDisplay: "exceptZero" }).format(value);
  return <strong className="whitespace-nowrap tabular-nums">{t(namespace + "points", { value: text })}</strong>;
}

function WeaponNotes({ unknown }: { unknown?: number }) {
  const { t } = useI18n();
  return <div className="space-y-1 text-xs text-slate-400">
    <p>{t(namespace + "weaponNotes")}</p>
    {unknown !== undefined && <p>{t(namespace + "unknownSlots", { count: unknown })}</p>}
  </div>;
}

function Weapons({ data }: { data: StageAdoption["weapons"] }) {
  const { t } = useI18n();
  if (!data.commanders) return <p className="text-sm text-slate-400">{t("seasonSummary.noRegistrations")}</p>;
  return <>
    <table className={table}>
      <thead><tr>
        <th scope="col" className={cell + " w-[16%]"}>{t(namespace + "weapon")}</th>
        {metrics.map(metric => <th scope="col" className={cell} key={metric}>{t(namespace + metric)}</th>)}
      </tr></thead>
      <tbody>{data.weapons.map(row => <tr key={row.weapon}>
        <th scope="row" className={cell}>{row.weapon}</th>
        {metrics.map(metric => <td className={cell} key={metric}><Counts value={row[metric]} /></td>)}
      </tr>)}</tbody>
    </table>
    <WeaponNotes unknown={data.unknown_slots} />
  </>;
}

function TransitionScope({ title, scope }: { title: string; scope: WeaponTransition["current"] }) {
  const { t } = useI18n();
  return <div className="min-w-0 rounded-lg border border-white/10 p-2.5 text-sm">
    <h4 className="break-words font-semibold">{title}</h4>
    <p className="text-xs text-slate-300">{t(namespace + "cohortCounts", {
      tournaments: scope.tournaments, total: scope.public_tournaments, players: scope.commanders, slots: scope.slots,
    })}</p>
    <p className="text-xs text-slate-400">{t(namespace + "unknownSlots", { count: scope.unknown_slots })}</p>
    {scope.reason && <p className="mt-1 text-xs text-amber-200">{t(namespace + scope.reason)}</p>}
  </div>;
}

function TransitionTable({ transition, metric, previous, current }: {
  transition: WeaponTransition; metric: WeaponMetric; previous: string; current: string;
}) {
  const { t } = useI18n();
  return <table className={table}>
    <caption className="pb-1 text-left text-sm font-semibold">{t(namespace + metric)}</caption>
    <thead><tr>
      <th scope="col" className={cell + " w-[14%]"}>{t(namespace + "weapon")}</th>
      <th scope="col" className={cell + " break-words"}>{previous}</th>
      <th scope="col" className={cell + " break-words"}>{current}</th>
      <th scope="col" className={cell + " w-[20%]"}>{t(namespace + "change")}</th>
    </tr></thead>
    <tbody>{transition.weapons.map(row => <tr key={row.weapon}>
      <th scope="row" className={cell}>{row.weapon}</th>
      <td className={cell}><Counts value={row[metric].previous} /></td>
      <td className={cell}><Counts value={row[metric].current} /></td>
      <td className={cell}><Change value={row[metric].change_pt} /></td>
    </tr>)}</tbody>
  </table>;
}

export function TransitionPanel({ data }: { data: SummaryStatistics }) {
  const { t } = useI18n();
  const comparison = data.season_comparison;
  if (comparison.mode === "growth" || (comparison.mode === "unavailable" && !comparison.reason)) return null;
  return <details className={wrap} data-testid="summary-transition">
    <summary className={disclosure}>{t(namespace + "transition")}</summary>
    <div className="space-y-3 pb-4">
      {comparison.mode === "transition" ? <>
        <p className="text-sm text-slate-300">{t(namespace + "transitionScope")}</p>
        <div className="grid grid-cols-2 gap-2">
          <TransitionScope title={comparison.previous.name} scope={comparison.transition.previous} />
          <TransitionScope title={data.title} scope={comparison.transition.current} />
        </div>
        {metrics.map(metric => <TransitionTable key={metric} transition={comparison.transition}
          metric={metric} previous={comparison.previous.name} current={data.title} />)}
        <p className="text-xs text-slate-400">{t(namespace + "unroundedDifference")}</p>
        <WeaponNotes />
      </> : <p className="text-sm text-slate-400">{t(namespace + comparison.reason)}</p>}
    </div>
  </details>;
}

function Bursts({ data }: { data: StageAdoption["burst"] }) {
  const { t } = useI18n();
  const [burst, setBurst] = useState<keyof typeof burstLabels>("1");
  const groups = Object.keys(burstLabels) as (keyof typeof burstLabels)[];
  const rows = data.groups[burst];
  return <>
    <div role="group" aria-label={t(namespace + "burst")} className="flex flex-wrap gap-2">
      {groups.map(key => <button key={key} type="button" aria-pressed={burst === key}
        onClick={() => setBurst(key)} className={selector}>{t(namespace + "burstLabel", { burst: burstLabels[key] })}</button>)}
    </div>
    <p className="text-xs text-slate-400">{t(namespace + "burstNotes")}</p>
    {!data.population ? <p className="text-sm text-slate-400">{t("seasonSummary.noRegistrations")}</p> :
      rows.length ? <ol className="grid gap-1.5">{rows.map(row =>
        <li key={row.id} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 px-3 py-2 text-sm">
          <span className="min-w-0 break-words">{row.name}</span><Counts value={row} />
        </li>,
      )}</ol> : <p className="text-sm text-slate-400">{t(namespace + "noBurstAdoption")}</p>}
  </>;
}

function GrowthList({ title, rows }: {
  title: string; rows: { key: string | number; label: ReactNode; change: AdoptionChange }[];
}) {
  const { t } = useI18n();
  return <div className="min-w-0 space-y-2">
    <h4 className="font-semibold">{title}</h4>
    {rows.length ? <ol className="grid gap-1.5">
      {rows.map(({ key, label, change }) => <li key={key} className="space-y-2 rounded-lg border border-white/10 px-3 py-2">
        <div className="text-sm font-medium">{label}</div>
        <dl className="grid grid-cols-3 items-start gap-1 text-xs">
          <div><dt className="text-slate-400">{t(namespace + "previous")}</dt><dd><Counts value={change.previous} /></dd></div>
          <div><dt className="text-slate-400">{t(namespace + "current")}</dt><dd><Counts value={change.current} /></dd></div>
          <div><dt className="text-slate-400">{t(namespace + "change")}</dt><dd><Change value={change.change_pt} /></dd></div>
        </dl>
      </li>)}
    </ol> : <p className="text-sm text-slate-400">{t(namespace + "noGrowth")}</p>}
  </div>;
}

function Growth({ data, current, previous, characters }: {
  data: StageGrowth; current: string; previous: string; characters: Character[];
}) {
  const { t } = useI18n();
  const reason = !data.previous_tournaments ? "noPreviousStage" :
    !data.previous_population ? "noPreviousRegistrations" : !data.current_population ? "noCurrentRegistrations" : null;
  return <>
    <p className="break-words text-sm text-slate-300">{t(namespace + "growthScope", {
      current, previous, currentCount: data.current_population, previousCount: data.previous_population,
    })}</p>
    {reason ? <p className="text-sm text-slate-400">{t(namespace + reason)}</p> : <>
      <p className="text-xs text-slate-400">{t(namespace + "unroundedDifference")}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <GrowthList title={t(namespace + "growingCharacters")}
          rows={data.characters.map(row => ({ key: row.id, label: row.name, change: row }))} />
        <GrowthList title={t(namespace + "growingTeams")} rows={data.teams.map(row => ({
          key: row.canonical_id, label: <TeamDisplay charIds={row.character_ids} allCharacters={characters} />, change: row,
        }))} />
      </div>
    </>}
  </>;
}

export function AdoptionPanel({ data, stage, characters }: {
  data: SummaryStatistics; stage: SummaryStage; characters: Character[];
}) {
  const { t } = useI18n();
  const [view, setView] = useState<"weapons" | "burst" | "growth">("weapons");
  const adoption = data.adoption_stages[stage];
  if (!adoption) return null;
  const comparison = data.season_comparison;
  const growth = comparison.mode === "growth" ? comparison.growth[stage] : undefined;
  const selected = view === "growth" && !growth ? "weapons" : view;
  return <details className={wrap} data-testid="summary-adoption">
    <summary className={disclosure}>
      {t(namespace + "title")} <span className="ml-1 text-sm font-normal text-slate-400">{t(summaryStageLabel(stage))}</span>
    </summary>
    <div className="space-y-3 pb-4">
      <div role="group" aria-label={t(namespace + "title")} className="flex flex-wrap gap-2">
        {(["weapons", "burst", ...(growth ? ["growth"] as const : [])] as const).map(key =>
          <button key={key} type="button" aria-pressed={selected === key} onClick={() => setView(key)}
            className={selector}>{t(namespace + key)}</button>,
        )}
      </div>
      {selected === "weapons" && <Weapons data={adoption.weapons} />}
      {selected === "burst" && <Bursts data={adoption.burst} />}
      {selected === "growth" && growth && comparison.mode === "growth" &&
        <Growth data={growth} current={data.title} previous={comparison.previous.name} characters={characters} />}
    </div>
  </details>;
}
