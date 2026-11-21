"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import type { SeasonArticles } from "@/lib/articles";
import { serverLabels, summaryEndpoint, type PlayServer, type SummaryStatistics } from "@/lib/seasonSummary";
import { PublishedArticleList, PublishedArticleView } from "./PublishedArticles";
import SeasonStatistics from "./SeasonStatistics";

type Championship = { id: number; label: string };
type Character = { id: number; name: string; is_template_available: boolean; icon_url?: string };

function useSummaryData<T>(url: string | null) {
  const [result, setResult] = useState<{ url: string; data: T | null }>();
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    fetch(url, { signal: controller.signal, cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error("Summary lookup failed");
        const data: T = await response.json();
        if (!controller.signal.aborted) setResult({ url, data });
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ url, data: null });
      });
    return () => controller.abort();
  }, [url]);
  return result?.url === url ? result.data : undefined;
}

export default function SeasonSummary({ championships, selectedId, onSelect, server, characters }: {
  championships: Championship[]; selectedId: number; onSelect: (id: number) => void;
  server: PlayServer; characters: Character[];
}) {
  const { t } = useI18n();
  const championshipId = championships.find(title => title.id === selectedId)?.id ?? championships[0]?.id;
  const statisticsUrl = championshipId ? summaryEndpoint(championshipId, server) : null;
  const statistics = useSummaryData<SummaryStatistics>(statisticsUrl);
  const articles = useSummaryData<SeasonArticles>(championshipId ? `/api/articles/season/${championshipId}` : null);
  const serverName = t(serverLabels[server]);

  return (
    <section aria-labelledby="summary-title" className="min-w-0 space-y-5 text-slate-100">
      <div className="space-y-3 rounded-2xl border border-white/10 bg-slate-950/70 p-4 sm:p-6">
        <h2 id="summary-title" className="text-xl font-bold">{t("seasonSummary.scope")}</h2>
        {championships.length > 1 && (
          <label className="block max-w-full space-y-1 text-sm text-slate-300">
            <span className="block">{t("articles.championship")}</span>
            <select aria-label={t("articles.championship")} value={championshipId} onChange={event => onSelect(Number(event.target.value))}
              className="min-h-11 max-w-full rounded-lg border border-white/15 bg-slate-800 px-3">
              {championships.map(title => <option key={title.id} value={title.id}>{title.label}</option>)}
            </select>
          </label>
        )}
        {statistics && (
          <p className="font-medium" data-testid="summary-scope">
            {statistics.title} <span aria-hidden="true">｜</span> {serverName} <span aria-hidden="true">｜</span>{" "}
            {t("seasonSummary.scopeCount", { total: statistics.tournament_count, full: statistics.full_64, eight: statistics.champion_8 })}
          </p>
        )}
        {!championshipId && <p className="text-slate-400">{t("seasonSummary.noChampionship")}</p>}
        {championshipId && statistics === undefined && <p role="status" className="text-slate-400">{t("articles.loading")}</p>}
        {statistics === null && <p role="alert" className="text-rose-300">{t("articles.loadError")}</p>}
      </div>
      {articles?.latest && (
        <div className="rounded-xl border border-sky-300/20 bg-sky-950/40 px-4 py-3">
          <p className="text-xs font-semibold text-sky-200">{t("articles.season")}</p>
          <a href="#latest-season-note" lang="ja" className="block break-words py-1 font-bold text-sky-300 underline">
            {articles.latest.title}
          </a>
        </div>
      )}
      {statistics && <SeasonStatistics key={statisticsUrl} data={statistics} characters={characters} />}
      {championshipId && (
        <section aria-labelledby="season-articles" className="min-w-0 space-y-5 border-t border-white/10 pt-5">
          <h2 id="season-articles" className="text-xl font-bold">{t("articles.season")}</h2>
          {articles === undefined && <p role="status" className="text-slate-400">{t("articles.loading")}</p>}
          {articles === null && <p role="alert" className="text-rose-300">{t("articles.loadError")}</p>}
          {articles?.latest ? (
            <>
              <PublishedArticleView article={articles.latest} inSummary anchor="latest-season-note" />
              {articles.earlier.length > 0 && (
                <section className="border-t border-white/10 pt-5">
                  <h3 className="font-bold">{t("articles.earlier")}</h3>
                  <PublishedArticleList articles={articles.earlier} />
                </section>
              )}
            </>
          ) : articles && <p className="text-slate-400">{t("articles.noPublicArticles")}</p>}
        </section>
      )}
    </section>
  );
}
