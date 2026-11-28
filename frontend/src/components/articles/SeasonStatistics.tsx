"use client";

import { useState } from "react";
import LocalizedLink from "@/components/LocalizedLink";
import TeamDisplay from "@/components/TeamDisplay";
import { NikkeBadge } from "./SeasonAdoption";
import SummaryHighlights from "@/components/SummaryHighlights";
import { useI18n } from "@/i18n/I18nProvider";
import {
  characterSummaryHref, compositionSummaryHref, summaryStageLabel,
  type DebutResults, type RankedTeam, type Scope, type SummaryCharacter, type SummaryStage, type SummaryStatistics,
} from "@/lib/seasonSummary";

type Character = SummaryCharacter;

const panel = "min-w-0 space-y-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4 sm:p-6";
const stageOrder: SummaryStage[] = ["league", "championship", "final", "legacy"];

function usePercent() {
  const { locale } = useI18n();
  const formatter = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 });
  return (value: number | null) => value == null ? "—" : formatter.format(value / 100);
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
  const fixedDecks = data.initial_stage === "legacy";
  const ranking = data.rankings[stage];
  if (!ranking) return null;
  const list = ranking.teams;
  const row = (team: RankedTeam) => <TeamRow key={team.canonical_id} team={team} stage={stage}
    ids={ranking.tournament_ids} scope={data} characters={characters} />;
  return (
    <section aria-labelledby="summary-ranks" className={panel}>
      <h3 id="summary-ranks" className="text-lg font-bold">{t(fixedDecks ? "seasonSummary.rankingWholeEvent" : "seasonSummary.ranking")}</h3>
      {!fixedDecks && (
        <div role="group" aria-label={t("teamMeaning.registrationPhase")} className="flex flex-wrap gap-2">
          {stageOrder.filter(key => data.rankings[key]).map(key => (
            <button key={key} type="button" aria-pressed={stage === key} onClick={() => setStage(key)}
              className="min-h-11 rounded-lg border border-white/15 px-3 py-2 text-sm font-medium text-slate-300 hover:bg-white/10 aria-pressed:border-sky-500 aria-pressed:bg-sky-900 aria-pressed:text-white">
              {t(summaryStageLabel(key))}
            </button>
          ))}
        </div>
      )}
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

function DebutNumbers({ data, characters }: { data: DebutResults; characters: Character[] }) {
  const { t } = useI18n();
  const percent = usePercent();
  return (
    <div className="space-y-2">
      <p className="text-sm text-slate-300">
        {t("seasonSummary.adopters", { count: data.count, total: data.population })} <strong className="ml-1 text-sky-300">{percent(data.rate)}</strong>
      </p>
      <p className="text-sm text-slate-300">{t("seasonSummary.characterRounds", {
        wins: data.wins, losses: data.losses, total: data.rounds, pct: percent(data.win_rate),
      })}</p>
      {data.partners.length > 0 && (
        <div className="space-y-1.5 pt-1">
          <h5 className="text-xs font-semibold text-slate-300">{t("seasonSummary.partners")}</h5>
          <ul className="grid grid-cols-4 gap-1">
            {data.partners.map(nikke => (
              <li key={nikke.id} className="min-w-0 text-center">
                <NikkeBadge nikke={nikke} characters={characters} />
                <span className="text-xs font-semibold text-sky-300 tabular-nums">{percent(nikke.rate)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function DebutPanel({ debut, characters }: { debut: NonNullable<SummaryStatistics["debut"]>; characters: Character[] }) {
  const { t } = useI18n();
  const official = debut.stage !== "legacy";
  return (
    <section aria-labelledby="summary-debut" className={panel}>
      <h3 id="summary-debut" className="text-lg font-bold">{t("seasonSummary.debut")}</h3>
      <ul className="grid items-start gap-3 lg:grid-cols-2">
        {debut.characters.map(character => {
          const identity = <>
            <span className="shrink-0" aria-hidden="true"><NikkeBadge nikke={character} characters={characters} iconOnly /></span>
            <span>{character.name}</span>
          </>;
          return (
            <li key={character.id} className="space-y-3 rounded-xl border border-white/10 bg-slate-900/70 p-3">
              <h4 className="break-words font-semibold text-slate-100">
                {!official && debut.tournament_ids.length ? (
                  <LocalizedLink href={characterSummaryHref(character.id, "legacy", debut.tournament_ids)} prefetch={false}
                    title={t(summaryStageLabel("legacy"))}
                    className="inline-flex items-center gap-2 text-sky-300 underline">
                    {identity}
                  </LocalizedLink>
                ) : <span className="inline-flex items-center gap-2">{identity}</span>}
              </h4>
              <div className="space-y-2" aria-label={t("seasonSummary.overall")}>
                <h5 className="text-sm font-semibold">{t("seasonSummary.overall")}</h5>
                <DebutNumbers data={character.sections.all} characters={characters} />
              </div>
              {official && (["league", "championship", "final"] as const).map(stage => {
                const ids = debut.tournament_ids_by_stage[stage] ?? [];
                const data = character.sections[stage];
                return (
                  <details key={stage} className="border-t border-white/10 pt-2">
                    <summary className="min-h-10 cursor-pointer py-2 text-sm font-medium">{t(summaryStageLabel(stage))}</summary>
                    {ids.length && data ? (
                      <div className="space-y-2 pb-2">
                        <DebutNumbers data={data} characters={characters} />
                        <LocalizedLink href={characterSummaryHref(character.id, stage, ids)} prefetch={false}
                          className="inline-block text-xs text-sky-300 underline">{t("seasonSummary.openCharacter")}</LocalizedLink>
                      </div>
                    ) : <p className="pb-2 text-sm text-slate-400">{t(debut.tournament_ids.length ? "seasonSummary.notApplicable" : "seasonSummary.noRegistrations")}</p>}
                  </details>
                );
              })}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function SeasonStatistics({ data, characters }: { data: SummaryStatistics; characters: Character[] }) {
  return (
    <div className="space-y-4">
      <SummaryHighlights data={data} characters={characters} detailsHref={(key, side) =>
        compositionSummaryHref(data, "all", data.tournament_ids, key, side)} />
      <RankingPanel data={data} characters={characters} />
      {data.debut && <DebutPanel debut={data.debut} characters={characters} />}
    </div>
  );
}
