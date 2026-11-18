"use client";

import { useEffect, useState } from "react";

export function useTeamSearchUsage(enabled: boolean, ids: number[], singleId?: number,
                                   playServer?: string, championshipId?: number) {
  const [usage, setUsage] = useState<{ id: number; count: number }[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const key = [...ids].sort((a, b) => a - b).join(",");
  const scope = JSON.stringify([key, singleId, playServer, championshipId]);
  const [loadedScope, setLoadedScope] = useState("");

  useEffect(() => {
    if (!enabled) return;
    setUsage([]);
    if (!key) {
      setState("ready");
      return;
    }
    setState("loading");
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
        setUsage(data.character_usage);
        setLoadedScope(scope);
        setState("ready");
      }
    }).catch(() => {
      if (!controller.signal.aborted) {
        setLoadedScope(scope);
        setState("error");
      }
    });
    return () => controller.abort();
  }, [enabled, key, singleId, playServer, championshipId, scope]);

  return { usage, state: key && loadedScope !== scope ? "loading" as const : state };
}
