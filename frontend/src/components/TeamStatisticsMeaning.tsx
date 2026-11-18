"use client";

import { useI18n } from "@/i18n/I18nProvider";
import { localizedTournamentResult, tournamentResultClass } from "@/lib/tournamentResult";

export type CommanderFinishCount = { result: string; count: number };
export type TeamMeaning = {
  registration_phase?: string;
  composition_best_result?: string | null;
  commander_best_result?: string | null;
  usage_history?: { stage: string; round_count: number }[];
  usage_history_status?: string;
  commander_results?: CommanderFinishCount[];
  best_result?: string | null;
};

export function RegistrationPhaseLabel({ phase }: { phase?: string }) {
  const { t } = useI18n();
  if (phase === "legacy") return <span>{t("teamMeaning.legacy")}</span>;
  return <span>{t("teamMeaning.registrationPhase")}: {phase && ["league", "championship", "final"].includes(phase) ? t(`arenaPhases.${phase}`) : t("common.unknown")}</span>;
}

export function CompositionBestResult({ team }: { team: TeamMeaning }) {
  const { t } = useI18n();
  return <div className="space-y-1">
    <div className="text-xs font-semibold text-slate-400">{t("teamMeaning.compositionBest")}</div>
    <CompositionResultBadge team={team}/>
  </div>;
}

export function CompositionResultBadge({team}: {team:TeamMeaning}) {
  const {t}=useI18n();
  return (
    <span className={`inline-block rounded-full px-3 py-1 text-sm font-extrabold ring-1 ${tournamentResultClass(team.composition_best_result)}`}>
      {team.composition_best_result ? localizedTournamentResult(team.composition_best_result, t) : "—"}
    </span>
  );
}

export function CommanderResultBadge({team}: {team:TeamMeaning}) {
  const {t}=useI18n();
  const result=team.commander_best_result ?? team.best_result;
  return <span className={`inline-block rounded-full px-3 py-1 text-sm font-extrabold ring-1 ${tournamentResultClass(result)}`}>{result ? localizedTournamentResult(result,t) : "—"}</span>;
}

export function TeamRegistrationUsage({ team }: { team: TeamMeaning }) {
  return <div className="mt-2 text-xs font-semibold text-blue-300"><RegistrationPhaseLabel phase={team.registration_phase}/></div>;
}

export function TeamBestResults({ team }: { team: TeamMeaning }) {
  return <div className="my-3 flex flex-wrap items-end gap-5">
    <CompositionBestResult team={team}/>
  </div>;
}

export const WIN_RATE_FILTER_CLASS = "h-10 rounded-lg border border-slate-600 bg-slate-800 px-3 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-60";

export function TeamResultFilters({ composition, onCompositionChange, stage, onStageChange, formal }: {
  composition: string; onCompositionChange: (value:string)=>void;
  stage: string; onStageChange: (value:string)=>void; formal: boolean;
}) {
  const { t } = useI18n();
  const optionLabel = (key:string, value:string) => t("teamMeaning.filterValue", {label:t(key), value});
  return <>
    <select aria-label={t("teamMeaning.registrationPhase")} className={WIN_RATE_FILTER_CLASS} value={formal ? stage : "all"} disabled={!formal} onChange={e=>onStageChange(e.target.value)}>
      <option value="all">{optionLabel("teamMeaning.registrationPhase",t("teamMeaning.allStages"))}</option>
      {formal && ["league","championship","final"].map(value=><option key={value} value={value}>{optionLabel("teamMeaning.registrationPhase",t(`arenaPhases.${value}`))}</option>)}
    </select>
    <select aria-label={t("teamMeaning.compositionBest")} className={WIN_RATE_FILTER_CLASS} value={composition} onChange={e=>onCompositionChange(e.target.value)}>
      <option value="">{optionLabel("teamMeaning.compositionBest",t("teamMeaning.anyResult"))}</option>
      {["champion","runner_up","finalist","best4","best8","best16","best32","best64"].map(value=>{
        const result = localizedTournamentResult(value,t) ?? value;
        return <option key={value} value={value}>{optionLabel("teamMeaning.compositionBest",value === "champion" ? result : t("teamMeaning.atLeast", {result}))}</option>;
      })}
    </select>
  </>;
}

export function TeamSearchFilters({composition,onCompositionChange,stage,onStageChange,formal,winRate,onWinRateChange,sort,onSortChange}: {
  composition:string;onCompositionChange:(value:string)=>void;stage:string;onStageChange:(value:string)=>void;formal:boolean;
  winRate:number;onWinRateChange:(value:number)=>void;
  sort:"count"|"win_rate"|"composition_best_result";onSortChange:(value:"count"|"win_rate"|"composition_best_result")=>void;
}) {
  const {t}=useI18n();
  return <div className="flex flex-wrap items-center gap-2">
    <select aria-label={t("teamMeaning.sort")} value={sort} onChange={e=>onSortChange(e.target.value as typeof sort)} className={WIN_RATE_FILTER_CLASS}>
      {["count","win_rate","composition_best_result"].map(value=><option key={value} value={value}>{t("teamMeaning.filterValue",{label:t("teamMeaning.sort"),value:t(`teamMeaning.sort.${value}`)})}</option>)}
    </select>
    <TeamResultFilters composition={composition} onCompositionChange={onCompositionChange} stage={stage} onStageChange={onStageChange} formal={formal}/>
    <select aria-label={t("stats.winRate")} value={winRate} onChange={e=>onWinRateChange(Number(e.target.value))} className={WIN_RATE_FILTER_CLASS}>
      <option value={0}>{t("filter.winRateAny")}</option>
      {[50,60,70,80].map(rate=><option key={rate} value={rate}>{t("filter.winRateAtLeast",{rate})}</option>)}
    </select>
  </div>;
}
