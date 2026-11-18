"use client";

import { useEffect, useState } from "react";

export function useTeamSearchUsage(enabled: boolean, ids: number[], singleId?: number,
                                   playServer?: string, championshipId?: number) {
  const key = [...ids].sort((a, b) => a - b).join(",");
  const scopeKey = JSON.stringify([key, singleId, playServer, championshipId]);
  const [result, setResult] = useState<{ scopeKey: string; usage?: { id: number; count: number }[] }>();

  useEffect(() => {
    if (!enabled || !key) return;
    const controller = new AbortController();
    const url = singleId ? `/api/tournaments/${singleId}/dashboard/teams?registration_phase=all&character_usage=true`
      : "/api/dashboard/cross-tournament/teams";
    const options = singleId ? {} : { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tournament_ids: key.split(",").map(Number), play_server: playServer,
        championship_id: championshipId, registration_phase: "all", character_usage: true }) };
    fetch(url, { ...options, cache: "no-store", signal: controller.signal }).then(response => {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }).then(data => {
      if (!controller.signal.aborted) {
        setResult({ scopeKey, usage: data.character_usage });
      }
    }).catch(() => {
      if (!controller.signal.aborted) {
        setResult(previous => previous?.scopeKey === scopeKey && previous.usage ? previous : { scopeKey });
      }
    });
    return () => controller.abort();
  }, [enabled, key, singleId, playServer, championshipId, scopeKey]);

  const current = result?.scopeKey === scopeKey ? result : undefined;
  const state = !key || current?.usage ? "ready" : current ? "error" : "loading";
  return { usage: current?.usage ?? [], state } as const;
}
