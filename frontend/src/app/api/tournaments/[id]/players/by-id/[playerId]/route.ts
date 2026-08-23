import { NextRequest } from "next/server";
import { proxyBackend } from "../../../../../../../lib/backendProxy";
import { parsePositiveInteger } from "../../../../../../../lib/championProxyPolicy";

export const dynamic = "force-dynamic";
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string; playerId: string }> }) {
  const { id, playerId } = await params;
  const tournamentId = parsePositiveInteger(id); const parsedPlayerId = parsePositiveInteger(playerId);
  if (tournamentId == null || parsedPlayerId == null) return Response.json({ detail: "Invalid tournament or player id" }, { status: 422 });
  return proxyBackend(request, `/api/tournaments/${tournamentId}/players/by-id/${parsedPlayerId}`);
}
