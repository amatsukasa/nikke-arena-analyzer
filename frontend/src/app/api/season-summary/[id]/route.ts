import { NextRequest, NextResponse } from "next/server";
import { proxyBackend } from "@/lib/backendProxy";
import { isPlayServer } from "@/lib/seasonSummary";

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const server = request.nextUrl.searchParams.get("play_server");
  if (!/^[1-9]\d*$/.test(id) || !isPlayServer(server)) return new NextResponse(null, { status: 404 });
  const scopeOnly = request.nextUrl.searchParams.get("scope_only") === "true";
  return proxyBackend(request, `/api/season-summary/${id}?play_server=${server}&scope_only=${scopeOnly}`);
}
