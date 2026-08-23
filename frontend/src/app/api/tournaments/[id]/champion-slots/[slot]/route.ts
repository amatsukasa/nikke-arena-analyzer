import { NextRequest } from "next/server";
import { proxyBackend } from "../../../../../../lib/backendProxy";
import { parseChampionSlot, parsePositiveInteger } from "../../../../../../lib/championProxyPolicy";

export async function PUT(request: NextRequest, { params }: { params: Promise<{ id: string; slot: string }> }) {
  const { id, slot } = await params;
  const tournamentId = parsePositiveInteger(id); const championSlot = parseChampionSlot(slot);
  if (tournamentId == null || championSlot == null) return Response.json({ detail: "Invalid tournament id or champion slot" }, { status: 422 });
  return proxyBackend(request, `/api/tournaments/${tournamentId}/champion-slots/${championSlot}`);
}
