"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { isPlayServer, serverLabels, summaryEndpoint, type PlayServer, type ReferenceScope, type Scope } from "@/lib/seasonSummary";

export function ReferenceScopeText({ scope }: { scope: ReferenceScope }) {
  const { t } = useI18n();
  return <span>{t("seasonSummary.referenceScope", { server: t(serverLabels[scope.play_server]), count: scope.tournament_count })}</span>;
}

export default function ArticleReferenceScope({ championship, saved, pending, onCapture }: {
  championship: number; saved?: ReferenceScope; pending: PlayServer | null; onCapture: (server: PlayServer | null) => void;
}) {
  const { t } = useI18n();
  const [server, setServer] = useState<PlayServer | "">(pending ?? saved?.play_server ?? "");
  const [result, setResult] = useState<{ server: PlayServer; scope: Scope | null }>();
  useEffect(() => {
    if (!server) return;
    const controller = new AbortController();
    fetch(summaryEndpoint(championship, server, true), { signal: controller.signal, cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error("Scope lookup failed");
        const scope: Scope = await response.json();
        if (!controller.signal.aborted) setResult({ server, scope });
      })
      .catch(() => { if (!controller.signal.aborted) setResult({ server, scope: null }); });
    return () => controller.abort();
  }, [championship, server]);

  const live = result?.server === server ? result?.scope : undefined;
  return (
    <fieldset className="min-w-0 space-y-3 rounded-xl border border-white/15 p-3 text-sm">
      <legend className="px-1 font-medium">{t("seasonSummary.referenceTitle")}</legend>
      {saved && <p className="text-slate-200"><ReferenceScopeText scope={saved} /></p>}
      <label className="block">
        {t("seasonSummary.referenceServer")}
        <select aria-label={t("seasonSummary.referenceServer")} value={server} onChange={event => {
          const chosen = event.target.value;
          setServer(isPlayServer(chosen) ? chosen : "");
          onCapture(null);
        }} className="mt-1 block min-h-11 w-full rounded-lg border border-white/15 bg-slate-950 px-3">
          <option value="">{t("seasonSummary.chooseServer")}</option>
          {Object.keys(serverLabels).map((key: PlayServer) => <option key={key} value={key}>{t(serverLabels[key])}</option>)}
        </select>
      </label>
      {server && live === undefined && <p role="status" className="text-slate-400">{t("articles.loading")}</p>}
      {live === null && <p role="alert" className="text-rose-300">{t("articles.loadError")}</p>}
      {live && (
        <>
          <p className="text-slate-300">{t("seasonSummary.currentCount", { count: live.tournament_count })}</p>
          <button type="button" onClick={() => onCapture(pending ? null : live.play_server)}
            className="min-h-11 rounded-lg border border-white/15 px-3 text-sky-200 hover:bg-white/10">
            {t(pending ? "seasonSummary.cancelCapture" : "seasonSummary.capture")}
          </button>
          {pending && <p role="status" className="text-sky-200">{t("seasonSummary.capturePending")}</p>}
        </>
      )}
    </fieldset>
  );
}
