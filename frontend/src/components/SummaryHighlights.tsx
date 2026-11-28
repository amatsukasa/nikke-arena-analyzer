"use client";

import TeamDisplay from "@/components/TeamDisplay";
import { useI18n } from "@/i18n/I18nProvider";
import type { BattleSide, SummaryCharacter, SummaryHighlightsData } from "@/lib/seasonSummary";
import { WeaponAdoptionPanel } from "./articles/SeasonAdoption";

const panel = "min-w-0 space-y-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4 text-slate-100 sm:p-6";

export default function SummaryHighlights({ data, characters, detailsHref }: {
  data: SummaryHighlightsData;
  characters: SummaryCharacter[];
  detailsHref: (canonicalId: string, side: BattleSide) => string;
}) {
  const { t, href, locale } = useI18n();
  const { rounds, matches, side_leaders } = data;
  const format = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 });
  const attackShare = rounds.total ? rounds.attack / rounds.total : 0;

  return <>
    <section aria-labelledby="summary-rounds" className={panel}>
      <h3 id="summary-rounds" className="text-lg font-bold">{t("seasonSummary.roundShare")}</h3>
      {rounds.total ? (
        <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:gap-8">
          <div aria-hidden="true" className="flex size-36 shrink-0 items-center justify-center rounded-full sm:size-40"
            style={{ background: "conic-gradient(var(--color-blue-400) 0% " + (attackShare * 100)
              + "%, var(--color-red-400) " + (attackShare * 100) + "% 100%)" }}>
            <div className="grid size-[72%] place-content-center rounded-full bg-slate-950 text-center">
              <span className="text-2xl font-bold tabular-nums">{rounds.total.toLocaleString(locale)}</span>
              <span className="text-xs text-slate-400">{t("seasonSummary.roundLabel")}</span>
            </div>
          </div>
          <dl className="grid w-full min-w-0 gap-2 sm:max-w-sm">
            <div className="flex flex-wrap justify-between gap-x-3">
              <dt><span aria-hidden="true" className="mr-2 inline-block size-2 rounded-full bg-blue-400" />{t("seasonSummary.attack")}</dt>
              <dd className="font-semibold tabular-nums">{t("seasonSummary.sideWins", { wins: rounds.attack, pct: format.format(attackShare) })}</dd>
            </div>
            <div className="flex flex-wrap justify-between gap-x-3">
              <dt><span aria-hidden="true" className="mr-2 inline-block size-2 rounded-full bg-red-400" />{t("seasonSummary.defense")}</dt>
              <dd className="font-semibold tabular-nums">{t("seasonSummary.sideWins", { wins: rounds.defense, pct: format.format(rounds.defense / rounds.total) })}</dd>
            </div>
            <div className="flex flex-wrap justify-between gap-x-3 border-t border-white/10 pt-2 text-sm text-slate-300">
              <dt>{t("seasonSummary.roundLabel")}</dt>
              <dd className="tabular-nums">{rounds.total.toLocaleString(locale)}</dd>
            </div>
          </dl>
        </div>
      ) : <p className="text-slate-400">{t("seasonSummary.noRounds")}</p>}

      {rounds.total > 0 && <div className="space-y-2 border-t border-white/10 pt-3" data-testid="summary-side-picks">
        <p className="text-xs text-slate-400">{t("seasonSummary.sideMinimum", { count: side_leaders.minimum_rounds })}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {(["attack", "defense"] as const).map(side => {
            const [team] = side_leaders[side];
            const color = side === "attack" ? "text-blue-300" : "text-red-300";
            return <div key={side} className="min-w-0 space-y-1.5 rounded-xl border border-white/10 bg-slate-900/70 p-2.5"
              data-testid={"summary-pick-" + side}>
              <h4 className={"text-sm font-semibold " + color}>
                {t(side === "attack" ? "seasonSummary.attackLeaders" : "seasonSummary.defenseLeaders")}
              </h4>
              {team ? <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <TeamDisplay charIds={team.character_ids} allCharacters={characters} />
                  <span className="text-sm text-slate-300 tabular-nums">
                    {t("stats.winsLosses", { wins: team.wins, losses: team.losses })}{" "}
                    <strong className={color}>{format.format(team.win_rate / 100)}</strong>
                  </span>
                </div>
                {team.has_details && <a href={href(detailsHref(team.canonical_id, side))}
                  className="inline-block py-1 text-xs text-sky-300 underline">
                  {t("seasonSummary.openSideComposition", { side: t(side === "attack" ? "seasonSummary.attack" : "seasonSummary.defense") })}
                </a>}
              </> : <p className="text-xs text-slate-400">{t("seasonSummary.noQualifiedSideTeams")}</p>}
            </div>;
          })}
        </div>
      </div>}
      {matches.total > 0 && (
        <p className="text-sm text-slate-300">{t("seasonSummary.matchWins", { total: matches.total, wins: matches.attack })}</p>
      )}
    </section>
    <WeaponAdoptionPanel data={data.weapon_adoption} isBeta={data.initial_stage === "legacy"} characters={characters} />
  </>;
}
