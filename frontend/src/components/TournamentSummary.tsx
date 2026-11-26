"use client";

import SummaryHighlights from "./SummaryHighlights";
import type { SummaryCharacter, SummaryHighlightsData } from "@/lib/seasonSummary";

export default function TournamentSummary({ tournamentId, data, characters }: {
  tournamentId: number; data: SummaryHighlightsData; characters: SummaryCharacter[];
}) {
  return <div className="space-y-4">
    <SummaryHighlights data={data} characters={characters} detailsHref={(canonicalId, side) => {
      const params = new URLSearchParams({ tab: "matchups", teamKey: canonicalId, detail_phase: "all" });
      return "/tournament/" + tournamentId + "/dashboard?" + params + "#detail-" + side;
    }} />
  </div>;
}
