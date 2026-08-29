import { NextRequest } from "next/server";
import { proxyBackend } from "../../../../../../../../lib/backendProxy";
import { isAllowedChampionMethod, isChampionProxyAction, parsePositiveInteger } from "../../../../../../../../lib/championProxyPolicy";

type Context = { params: Promise<{ id: string; playerId: string; action: string }> };
async function forward(request: NextRequest, context: Context) {
  const { id, playerId, action } = await context.params;
  const tournamentId = parsePositiveInteger(id); const parsedPlayerId = parsePositiveInteger(playerId);
  if (tournamentId == null || parsedPlayerId == null) return Response.json({ detail: "Invalid tournament or player id" }, { status: 422 });
  if (!isChampionProxyAction(action)) return new Response("Not found", { status: 404 });
  if (!isAllowedChampionMethod(action, request.method)) return Response.json({ detail: "Method not allowed" }, { status: 405 });
  return proxyBackend(request, `/api/tournaments/${tournamentId}/players/by-id/${parsedPlayerId}/${action}`);
}
export const GET = forward;
export const PUT = forward;
export const POST = forward;
export const DELETE = forward;
