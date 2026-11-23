"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { getCharIconUrl } from "@/utils/charIcon";
import {
  summaryStageLabel, summaryWeapons, type Adoption, type BurstRanking,
  type SummaryStage, type Weapon, type WeaponAdoption,
} from "@/lib/seasonSummary";

type Character = { id: number; name: string; is_template_available: boolean; template_filename?: string; icon_url?: string };

const panel = "min-w-0 space-y-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4 sm:p-6";
const selector = "min-h-11 rounded-lg border border-white/15 px-3 text-sm text-slate-300 hover:bg-white/10 aria-pressed:border-sky-500 aria-pressed:bg-sky-900 aria-pressed:text-white";
const officialStages = ["league", "championship", "final"] as const;
const burstLabels = { "1": "Ⅰ", "2": "Ⅱ", "3": "Ⅲ" } as const;
const colors = {
  SG: "#34d9ce", SR: "#a9a4ff", AR: "#6ba7ff", MG: "#fb9d68",
  RL: "#d888ea", SMG: "#d4ca6a", unknown: "#94a3b8",
};

function useNumberFormats() {
  const { locale } = useI18n();
  return {
    count: new Intl.NumberFormat(locale),
    percent: new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }),
  };
}

export function NikkeBadge({ nikke, characters, iconOnly = false }: {
  nikke: { id: number; name: string }; characters: Character[]; iconOnly?: boolean;
}) {
  const [failedUrl, setFailedUrl] = useState("");
  const url = getCharIconUrl(characters.find(character => character.id === nikke.id));
  return (
    <span className="flex min-w-0 flex-col items-center gap-1 text-center" title={nikke.name}>
      <span className="flex size-9 items-center justify-center overflow-hidden rounded-lg border border-white/10 bg-slate-800 sm:size-10">
        {url && failedUrl !== url ? (
          <img src={url} alt="" loading="lazy" decoding="async" onError={() => setFailedUrl(url)} className="size-full object-cover" />
        ) : <span aria-hidden="true" className="text-[10px] text-slate-300">{nikke.name.slice(0, 3)}</span>}
      </span>
      {!iconOnly && <span className="break-words text-[11px] leading-tight text-slate-300">{nikke.name}</span>}
    </span>
  );
}

function WeaponPie({ stage, data, selected }: {
  stage: SummaryStage; data: WeaponAdoption["by_stage"][SummaryStage]; selected: Weapon;
}) {
  const { t } = useI18n();
  const { count, percent } = useNumberFormats();
  const label = t(summaryStageLabel(stage));
  const slots = data?.slots ?? 0;

  let pie = null;
  if (data && slots) {
    const categories = [...summaryWeapons, "unknown"] as const;
    const highlight = categories.indexOf(selected);
    const ordered = [...categories.slice(highlight), ...categories.slice(0, highlight)];
    let used = 0;
    const segments = ordered.filter(weapon => data.counts[weapon] > 0).map(weapon => {
      const start = used / slots * 100;
      used += data.counts[weapon];
      const color = weapon === selected ? colors[weapon] : "color-mix(in srgb, " + colors[weapon] + " 63%, #111827)";
      return color + " " + start + "% " + used / slots * 100 + "%";
    });
    const breakdown = categories.map(weapon => {
      const name = weapon === "unknown" ? t("common.unknown") : weapon;
      return name + " " + percent.format(data.counts[weapon] / slots);
    }).join(" · ");
    pie = <>
      <div role="img" aria-label={label + " · " + breakdown} title={breakdown}
        className="mx-auto grid aspect-square w-full max-w-32 place-items-center rounded-full"
        style={{ background: "conic-gradient(" + segments.join(", ") + ")" }}>
        <div className="grid size-[71%] content-center place-items-center rounded-full bg-slate-950 leading-tight">
          <span className="text-[11px] font-semibold sm:text-sm" style={{ color: colors[selected] }}>{selected}</span>
          <strong data-testid="weapon-share" className="text-sm tabular-nums sm:text-xl">{percent.format(data.counts[selected] / slots)}</strong>
        </div>
      </div>
      <p className="text-[11px] tabular-nums text-slate-300 sm:text-xs">{t("seasonAdoption.slotFraction", {
        count: count.format(data.counts[selected]), total: count.format(slots),
      })}</p>
    </>;
  }

  return <figure data-testid={"weapon-pie-" + stage}
    className="min-w-0 space-y-2 rounded-xl border border-white/10 bg-slate-900/70 px-1.5 py-2.5 text-center sm:px-4 sm:py-3">
    <figcaption className="flex min-h-9 items-center justify-center text-xs font-semibold leading-tight sm:min-h-10 sm:text-sm">
      {label}
    </figcaption>
    {pie ?? <div className="mx-auto grid aspect-square w-full max-w-32 place-items-center rounded-full border border-dashed border-white/15 px-1 text-[11px] text-slate-400 sm:text-xs">
      {t("seasonSummary.noRegistrations")}
    </div>}
  </figure>;
}

export function WeaponAdoptionPanel({ data, isBeta, characters }: {
  data: WeaponAdoption; isBeta: boolean; characters: Character[];
}) {
  const { t } = useI18n();
  const { count, percent } = useNumberFormats();
  const [selected, setSelected] = useState<Weapon>("SG");
  const stages = isBeta ? (["legacy"] as const) : officialStages;
  const ranked = data.rankings[selected];
  const unknown = Object.values(data.by_stage).reduce((total, stage) => total + (stage?.counts.unknown ?? 0), 0);

  return <section aria-labelledby="summary-weapons" className={panel}>
    <h3 id="summary-weapons" className="text-lg font-bold">{t("seasonAdoption.weaponShare")}</h3>
    <div id="weapon-stage-charts" className={isBeta ? "grid max-w-52 gap-2" : "grid grid-cols-3 gap-2 sm:gap-3"}>
      {stages.map(stage => <WeaponPie key={stage} stage={stage} data={data.by_stage[stage]} selected={selected} />)}
    </div>
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t("seasonAdoption.weapon")}>
      {summaryWeapons.map(weapon => <button type="button" key={weapon} aria-pressed={weapon === selected}
        aria-controls="weapon-stage-charts weapon-rankings"
        className={selector + " inline-flex items-center gap-1.5 px-2 sm:px-3"} onClick={() => setSelected(weapon)}>
        <span className="size-2 shrink-0 rounded-full" aria-hidden="true" style={{ backgroundColor: colors[weapon] }} />{weapon}
      </button>)}
      {unknown > 0 && <span className="inline-flex items-center gap-1.5 text-xs text-slate-300">
        <span className="size-2 rounded-full" aria-hidden="true" style={{ backgroundColor: colors.unknown }} />{t("common.unknown")}
      </span>}
    </div>
    <div id="weapon-rankings" className="space-y-2 border-t border-white/10 pt-4">
      <h4 className="text-base font-bold">{t("seasonAdoption.weaponRanking")}</h4>
      {data.slots > 0 && <p className="text-xs text-slate-400">{t("seasonAdoption.weaponRankingScope", { total: count.format(data.slots) })}</p>}
      {unknown > 0 && <p className="text-xs text-slate-400">{t("seasonAdoption.unknownSlots", { count: count.format(unknown) })}</p>}
      {ranked.length ? <ol data-testid="weapon-nikke-ranking" className="divide-y divide-white/10">
        {ranked.map((row, index) => <li key={row.id} className="flex items-center gap-2 py-1.5 text-sm">
          <span className="w-4 shrink-0 text-center text-xs tabular-nums text-slate-400">{index + 1}</span>
          <span aria-hidden="true"><NikkeBadge nikke={row} characters={characters} iconOnly /></span>
          <span className="min-w-0 flex-1 break-words">{row.name}</span>
          <strong className="shrink-0 tabular-nums" style={{ color: colors[selected] }}
            title={t("seasonAdoption.slotFraction", { count: count.format(row.count), total: count.format(row.population) })}>
            {row.rate === null ? "—" : percent.format(row.rate / 100)}
          </strong>
        </li>)}
      </ol> : <p className="text-sm text-slate-400">{t(data.slots ? "seasonAdoption.noWeaponAdoption" : "seasonSummary.noRegistrations")}</p>}
    </div>
  </section>;
}

function Counts({ value }: { value: Adoption }) {
  const { count, percent } = useNumberFormats();
  if (value.rate === null) return <span className="text-slate-400">—</span>;
  return <span className="tabular-nums">
    <strong className="block text-sky-200">{percent.format(value.rate / 100)}</strong>
    <span className="text-slate-300">{count.format(value.count)} / {count.format(value.population)}</span>
  </span>;
}

export function BurstPanel({ data, stage }: { data: BurstRanking; stage: SummaryStage }) {
  const { t } = useI18n();
  const [burst, setBurst] = useState<keyof typeof burstLabels>("1");
  const groups = Object.keys(burstLabels) as (keyof typeof burstLabels)[];
  const rows = data.groups[burst];
  return <details className="min-w-0 rounded-2xl border border-white/10 bg-slate-950/60 px-4 sm:px-6">
    <summary className="min-h-11 cursor-pointer py-3 font-bold">
      {t("seasonAdoption.burst")} <span className="ml-1 text-sm font-normal text-slate-400">{t(summaryStageLabel(stage))}</span>
    </summary>
    <div className="space-y-3 pb-4">
      <div role="group" aria-label={t("seasonAdoption.burst")} className="flex flex-wrap gap-2">
        {groups.map(key => <button key={key} type="button" aria-pressed={burst === key}
          onClick={() => setBurst(key)} className={selector}>{t("seasonAdoption.burstLabel", { burst: burstLabels[key] })}</button>)}
      </div>
      <p className="text-xs text-slate-400">{t("seasonAdoption.burstNotes")}</p>
      {!data.population ? <p className="text-sm text-slate-400">{t("seasonSummary.noRegistrations")}</p> :
        rows.length ? <ol className="grid gap-1.5">{rows.map(row =>
          <li key={row.id} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 px-3 py-2 text-sm">
            <span className="min-w-0 break-words">{row.name}</span><Counts value={row} />
          </li>,
        )}</ol> : <p className="text-sm text-slate-400">{t("seasonAdoption.noBurstAdoption")}</p>}
    </div>
  </details>;
}
