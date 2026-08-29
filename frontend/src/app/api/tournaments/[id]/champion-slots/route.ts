import { NextRequest } from "next/server";
import { proxyBackend } from "../../../../../lib/backendProxy";
import { parsePositiveInteger } from "../../../../../lib/championProxyPolicy";

export const dynamic = "force-dynamic";
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const tournamentId = parsePositiveInteger(id);
  if (tournamentId == null) return Response.json({ detail: "Invalid tournament id" }, { status: 422 });
  return proxyBackend(request, `/api/tournaments/${tournamentId}/champion-slots`);
}
