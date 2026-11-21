"use client";

import { useState } from "react";
import LocalizedLink from "@/components/LocalizedLink";
import TeamDisplay from "@/components/TeamDisplay";
import { useI18n } from "@/i18n/I18nProvider";
import { getCharIconUrl } from "@/utils/charIcon";
import {
  characterSummaryHref, compositionSummaryHref, summaryStageLabel,
  type DebutResults, type RankedTeam, type Scope, type SideLeaders, type SummaryStage, type SummaryStatistics,
} from "@/lib/seasonSummary";

type Character = { id: number; name: string; is_template_available: boolean; template_filename?: string; icon_url?: string };

const panel = "min-w-0 space-y-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4 sm:p-6";
const stageOrder: SummaryStage[] = ["league", "championship", "final", "legacy"];

function usePercent() {
  const { locale } = useI18n();
  const formatter = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 });
  return (value: number | null) => value == null ? "—" : formatter.format(value / 100);
}

function NikkeBadge({ nikke, characters }: { nikke: { id: number; name: string }; characters: Character[] }) {
  const [failedUrl, setFailedUrl] = useState("");
  const url = getCharIconUrl(characters.find(character => character.id === nikke.id));
  return (
    <div className="flex min-w-0 flex-col items-center gap-1 text-center" title={nikke.name}>
      <div className="flex size-9 items-center justify-center overflow-hidden rounded-lg border border-white/10 bg-slate-800 sm:size-10">
        {url && failedUrl !== url ? (
          <img src={url} alt="" loading="lazy" decoding="async" onError={() => setFailedUrl(url)} className="size-full object-cover" />
        ) : <span aria-hidden="true" className="text-[10px] text-slate-300">{nikke.name.slice(0, 3)}</span>}
      </div>
      <span className="break-words text-[11px] leading-tight text-slate-300">{nikke.name}</span>
    </div>
  );
}

function SideLeaderList({ leaders, characters }: { leaders: SideLeaders; characters: Character[] }) {
  const { t } = useI18n();
  const percent = usePercent();
  if (!leaders.attack.length && !leaders.defense.length) return null;
  return (
    <div className="space-y-3 border-t border-white/10 pt-4">
      <p className="text-xs text-slate-400">{t("seasonSummary.sideMinimum", { count: leaders.minimum_rounds })}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        {(["attack", "defense"] as const).map(side => (
          <div key={side} className="space-y-2">
            <h4 className={`text-sm font-semibold ${side === "attack" ? "text-blue-400" : "text-red-400"}`}>
              {t(side === "attack" ? "seasonSummary.attackLeaders" : "seasonSummary.defenseLeaders")}
            </h4>
            {leaders[side].length ? (
              <ol className="grid grid-cols-5 gap-1">
                {leaders[side].map(nikke => (
                  <li key={nikke.id} className="min-w-0 text-center">
                    <NikkeBadge nikke={nikke} characters={characters} />
                    <span className="text-xs text-slate-200 tabular-nums" title={`${nikke.wins}/${nikke.rounds}`}>{percent(nikke.win_rate)}</span>
                  </li>
                ))}
              </ol>
            ) : <p className="text-sm text-slate-400">{t("seasonSummary.noRounds")}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

function SideResults({ rounds, matches, side_leaders, characters }: Pick<SummaryStatistics, "rounds" | "matches" | "side_leaders"> & {
  characters: Character[];
}) {
  const { t } = useI18n();
  const percent = usePercent();
  const attackShare = rounds.total ? 100 * rounds.attack / rounds.total : 0;
  return (
    <section aria-labelledby="summary-rounds" className={panel}>
      <h3 id="summary-rounds" className="text-lg font-bold">{t("seasonSummary.roundShare")}</h3>
      {rounds.total ? (
        <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:gap-8">
          <div aria-hidden="true" className="flex size-36 shrink-0 items-center justify-center rounded-full sm:size-40"
            style={{ background: `conic-gradient(var(--color-blue-400) 0% ${attackShare}%, var(--color-red-400) ${attackShare}% 100%)` }}>
            <div className="grid size-[72%] place-content-center rounded-full bg-slate-950 text-center">
              <span className="text-2xl font-bold tabular-nums">{rounds.total.toLocaleString()}</span>
              <span className="text-xs text-slate-400">{t("seasonSummary.roundLabel")}</span>
            </div>
          </div>
          <dl className="grid w-full min-w-0 gap-2 sm:max-w-sm">
            <div className="flex flex-wrap justify-between gap-x-3">
              <dt><span aria-hidden="true" className="mr-2 inline-block size-2 rounded-full bg-blue-400" />{t("seasonSummary.attack")}</dt>
              <dd className="font-semibold tabular-nums">{t("seasonSummary.sideWins", { wins: rounds.attack, pct: percent(attackShare) })}</dd>
            </div>
            <div className="flex flex-wrap justify-between gap-x-3">
              <dt><span aria-hidden="true" className="mr-2 inline-block size-2 rounded-full bg-red-400" />{t("seasonSummary.defense")}</dt>
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
      <SideLeaderList leaders={side_leaders} characters={characters} />
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
  const fixedDecks = data.initial_stage === "legacy";
  const [stage, setStage] = useState(data.initial_stage);
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
        {debut.characters.map(character => (
          <li key={character.id} className="space-y-3 rounded-xl border border-white/10 bg-slate-900/70 p-3">
            <h4 className="break-words font-semibold text-slate-100">
              {debut.tournament_ids.length ? (
                <LocalizedLink href={characterSummaryHref(character.id, debut.stage, debut.tournament_ids)} prefetch={false}
                  title={t(summaryStageLabel(debut.stage))}
                  className="inline-flex items-center gap-2 text-sky-300 underline">
                  <div aria-hidden="true"><TeamDisplay charIds={[character.id]} allCharacters={characters} /></div>
                  {character.name}
                </LocalizedLink>
              ) : character.name}
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
        ))}
      </ul>
    </section>
  );
}

export default function SeasonStatistics({ data, characters }: { data: SummaryStatistics; characters: Character[] }) {
  return (
    <div className="space-y-4">
      <SideResults rounds={data.rounds} matches={data.matches} side_leaders={data.side_leaders} characters={characters} />
      <RankingPanel data={data} characters={characters} />
      {data.debut && <DebutPanel debut={data.debut} characters={characters} />}
    </div>
  );
}
