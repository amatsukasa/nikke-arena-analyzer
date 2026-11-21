"use client";

import { useState } from "react";
import LocalizedLink from "@/components/LocalizedLink";
import TeamDisplay from "@/components/TeamDisplay";
import { useI18n } from "@/i18n/I18nProvider";
import {
  characterSummaryHref, compositionSummaryHref, summaryStageLabel,
  type RankedTeam, type Scope, type SummaryStage, type SummaryStatistics,
} from "@/lib/seasonSummary";

type Character = { id: number; name: string; is_template_available: boolean; template_filename?: string; icon_url?: string };

const panel = "min-w-0 space-y-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4 sm:p-6";
const stageOrder: SummaryStage[] = ["league", "championship", "final", "legacy"];

function usePercent() {
  const { locale } = useI18n();
  const formatter = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 });
  return (value: number | null) => value == null ? "—" : formatter.format(value / 100);
}

function SideResults({ rounds, matches }: Pick<SummaryStatistics, "rounds" | "matches">) {
  const { t } = useI18n();
  const percent = usePercent();
  const attackShare = rounds.total ? 100 * rounds.attack / rounds.total : 0;
  return (
    <section aria-labelledby="summary-rounds" className={panel}>
      <h3 id="summary-rounds" className="text-lg font-bold">{t("seasonSummary.roundShare")}</h3>
      {rounds.total ? (
        <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:gap-8">
          <div aria-hidden="true" className="flex size-36 shrink-0 items-center justify-center rounded-full sm:size-40"
            style={{ background: `conic-gradient(#2dd4bf 0% ${attackShare}%, #a78bfa ${attackShare}% 100%)` }}>
            <div className="grid size-[72%] place-content-center rounded-full bg-slate-950 text-center">
              <span className="text-2xl font-bold tabular-nums">{rounds.total.toLocaleString()}</span>
              <span className="text-xs text-slate-400">{t("seasonSummary.roundLabel")}</span>
            </div>
          </div>
          <dl className="grid w-full min-w-0 gap-2 sm:max-w-sm">
            <div className="flex flex-wrap justify-between gap-x-3">
              <dt><span aria-hidden="true" className="mr-2 inline-block size-2 rounded-full bg-teal-400" />{t("seasonSummary.attack")}</dt>
              <dd className="font-semibold tabular-nums">{t("seasonSummary.sideWins", { wins: rounds.attack, pct: percent(attackShare) })}</dd>
            </div>
            <div className="flex flex-wrap justify-between gap-x-3">
              <dt><span aria-hidden="true" className="mr-2 inline-block size-2 rounded-full bg-violet-400" />{t("seasonSummary.defense")}</dt>
              <dd className="font-semibold tabular-nums">{t("seasonSummary.sideWins", { wins: rounds.defense, pct: percent(100 - attackShare) })}</dd>
            </div>
            <div className="flex flex-wrap justify-between gap-x-3 border-t border-white/10 pt-2 text-sm text-slate-300">
              <dt>{t("seasonSummary.roundLabel")}</dt><dd className="tabular-nums">{rounds.total.toLocaleString()}</dd>
            </div>
          </dl>
        </div>
      ) : <p className="text-slate-400">{t("seasonSummary.noRounds")}</p>}
      {matches.total > 0 && (
        <p className="text-sm text-slate-300">{t("seasonSummary.matchWins", { total: matches.total, wins: matches.attack })}</p>
      )}
    </section>
  );
}

function TeamRow({ team, stage, ids, scope, characters }: {
  team: RankedTeam; stage: SummaryStage; ids: number[]; scope: Scope; characters: Character[];
}) {
  const { t, href } = useI18n();
  const percent = usePercent();
  return (
    <li className="space-y-2 rounded-xl border border-white/10 bg-slate-900/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <div className="flex items-center gap-2">
          <span className="shrink-0 text-sm font-bold text-slate-300">{t("seasonSummary.place", { rank: team.rank })}</span>
          <TeamDisplay charIds={team.character_ids} allCharacters={characters} />
        </div>
        <span className="text-sm text-slate-300 tabular-nums">{t("seasonSummary.adopters", { count: team.count, total: team.population })} <strong className="ml-1 text-sky-300">{percent(team.rate)}</strong></span>
      </div>
      <a href={href(compositionSummaryHref(scope, stage, ids, team.canonical_id))}
        className="inline-block py-1 text-sm text-sky-300 underline">{t("seasonSummary.openComposition")}</a>
      {team.earlier && (
        <details className="text-sm text-slate-300">
          <summary className="cursor-pointer py-1">{t("seasonSummary.earlierAdoption")}</summary>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            {(["league", "championship"] as const).map(earlier => {
              const entry = team.earlier?.[earlier];
              return <span key={earlier}>{t(summaryStageLabel(earlier))} {percent(entry?.rate ?? null)}
                {entry && entry.population > 0 && ` (${entry.count}/${entry.population})`}</span>;
            })}
          </div>
        </details>
      )}
    </li>
  );
}

function RankingPanel({ data, characters }: { data: SummaryStatistics; characters: Character[] }) {
  const { t } = useI18n();
  const [stage, setStage] = useState(data.initial_stage);
  const ranking = data.rankings[stage];
  if (!ranking) return null;
  const list = ranking.teams;
  const row = (team: RankedTeam) => <TeamRow key={team.canonical_id} team={team} stage={stage}
    ids={ranking.tournament_ids} scope={data} characters={characters} />;
  return (
    <section aria-labelledby="summary-ranks" className={panel}>
      <h3 id="summary-ranks" className="text-lg font-bold">{t("seasonSummary.ranking")}</h3>
      <div role="group" aria-label={t("teamMeaning.registrationPhase")} className="flex flex-wrap gap-2">
        {stageOrder.filter(key => data.rankings[key]).map(key => (
          <button key={key} type="button" aria-pressed={stage === key} onClick={() => setStage(key)}
            className="min-h-11 rounded-lg border border-white/15 px-3 py-2 text-sm font-medium text-slate-300 hover:bg-white/10 aria-pressed:border-sky-500 aria-pressed:bg-sky-900 aria-pressed:text-white">
            {t(summaryStageLabel(key))}
          </button>
        ))}
      </div>
      <p className="text-sm text-slate-300">{t("seasonSummary.population", { total: ranking.population })}</p>
      {!ranking.tournament_ids.length ? (
        <p className="text-slate-400">{t(data.tournament_count ? "seasonSummary.notApplicable" : "seasonSummary.noRegistrations")}</p>
      ) : !ranking.population ? (
        <p className="text-slate-400">{t("seasonSummary.noRegistrations")}</p>
      ) : list.length > 0 ? (
        <>
          <ol className="grid gap-2">{list.slice(0, 5).map(row)}</ol>
          {list.length > 5 && (
            <details>
              <summary className="cursor-pointer py-2 text-sm text-sky-300">{t("seasonSummary.moreTies", { count: list.length - 5 })}</summary>
              <ol className="mt-2 grid gap-2">{list.slice(5).map(row)}</ol>
            </details>
          )}
        </>
      ) : <p className="text-slate-400">{t("seasonSummary.noCompositions")}</p>}
    </section>
  );
}

function DebutPanel({ debut, characters }: { debut: NonNullable<SummaryStatistics["debut"]>; characters: Character[] }) {
  const { t } = useI18n();
  const percent = usePercent();
  return (
    <section aria-labelledby="summary-debut" className={panel}>
      <header>
        <h3 id="summary-debut" className="text-lg font-bold">{t("seasonSummary.debut")}</h3>
        <p className="mt-1 text-sm text-slate-400">{t("teamMeaning.registrationPhase")} · {t(summaryStageLabel(debut.stage))}</p>
      </header>
      <ul className="grid gap-3 sm:grid-cols-2">
        {debut.characters.map(character => (
          <li key={character.id} className="space-y-2 rounded-xl border border-white/10 bg-slate-900/70 p-3">
            {debut.tournament_ids.length ? (
              <LocalizedLink href={characterSummaryHref(character.id, debut.stage, debut.tournament_ids)} prefetch={false}
                className="inline-flex items-center gap-2 text-sky-300 underline">
                <div aria-hidden="true"><TeamDisplay charIds={[character.id]} allCharacters={characters} /></div>
                {character.name}
              </LocalizedLink>
            ) : <span className="font-semibold">{character.name}</span>}
            <p className="text-sm text-slate-300">{t("seasonSummary.adopters", { count: character.count, total: character.population })} <strong className="ml-1 text-sky-300">{percent(character.rate)}</strong></p>
            <p className="text-sm text-slate-300">{t("seasonSummary.characterRounds", {
              wins: character.wins, losses: character.losses, total: character.rounds, pct: percent(character.win_rate),
            })}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function SeasonStatistics({ data, characters }: { data: SummaryStatistics; characters: Character[] }) {
  return (
    <div className="space-y-4">
      <SideResults rounds={data.rounds} matches={data.matches} />
      <RankingPanel data={data} characters={characters} />
      {data.debut && <DebutPanel debut={data.debut} characters={characters} />}
    </div>
  );
}
