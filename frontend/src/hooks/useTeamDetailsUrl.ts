"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

export function useTeamDetailsUrl() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTeam = searchParams.get("teamKey") || searchParams.get("team") || "";
  const initialSynergy = (searchParams.get("synergy") ?? "").split(",")
    .map(value => parseInt(value.trim(), 10)).filter(value => !Number.isNaN(value));

  function writeTeamDetailsUrl(canonicalId: string, phase: string, includedIds: number[], tournamentIds?: number[]) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "matchups");
    params.set("detail_phase", phase);
    params.set("team", canonicalId);
    params.set("teamKey", canonicalId);
    if (tournamentIds?.length) params.set("tournaments", tournamentIds.join(","));
    if (includedIds.length) params.set("synergy", includedIds.join(","));
    else params.delete("synergy");
    router.push(`${pathname}?${params}`, { scroll: false });
  }

  return { initialTeam, initialSynergy, writeTeamDetailsUrl };
}
