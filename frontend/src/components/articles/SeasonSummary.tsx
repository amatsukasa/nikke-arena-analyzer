"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import type { SeasonArticles } from "@/lib/articles";
import { PublishedArticleList, PublishedArticleView } from "./PublishedArticles";

type Championship = { id: number; label: string };

export default function SeasonSummary({ championships, preferredId }: { championships: Championship[]; preferredId: number }) {
  const { t } = useI18n();
  const [selectedId, setSelectedId] = useState(preferredId);
  const championshipId = championships.find(title => title.id === selectedId)?.id ?? championships[0]?.id;
  const [result, setResult] = useState<{ id: number; data: SeasonArticles | null }>();
  useEffect(() => {
    if (!championshipId) return;
    const controller = new AbortController();
    fetch(`/api/articles/season/${championshipId}`, { signal: controller.signal, cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error("Season article lookup failed");
        const data: SeasonArticles = await response.json();
        if (!controller.signal.aborted) setResult({ id: championshipId, data });
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ id: championshipId, data: null });
      });
    return () => controller.abort();
  }, [championshipId]);

  const data = result?.id === championshipId ? result?.data : undefined;
  return (
    <section aria-labelledby="season-articles" className="min-w-0 space-y-5">
      <h2 id="season-articles" className="text-xl font-bold">{t("articles.season")}</h2>
      {championships.length > 1 && (
        <label className="block max-w-full space-y-1 text-sm text-slate-300">
          <span className="block">{t("articles.championship")}</span>
          <select aria-label={t("articles.championship")} value={championshipId} onChange={event => setSelectedId(Number(event.target.value))}
            className="min-h-11 max-w-full rounded-lg border border-white/15 bg-slate-800 px-3">
            {championships.map(title => <option key={title.id} value={title.id}>{title.label}</option>)}
          </select>
        </label>
      )}
      {!championshipId && <p className="text-slate-400">{t("articles.noPublicArticles")}</p>}
      {championshipId && data === undefined && <p role="status" className="text-slate-400">{t("articles.loading")}</p>}
      {data === null && <p role="alert" className="text-rose-300">{t("articles.loadError")}</p>}
      {data && (
        data.latest ? (
          <>
            <PublishedArticleView article={data.latest} inSummary />
            {data.earlier.length > 0 && (
              <section className="mt-8 border-t border-white/10 pt-5">
                <h3 className="font-bold">{t("articles.earlier")}</h3>
                <PublishedArticleList articles={data.earlier} />
              </section>
            )}
          </>
        ) : <p className="text-slate-400">{t("articles.noPublicArticles")}</p>
      )}
    </section>
  );
}
