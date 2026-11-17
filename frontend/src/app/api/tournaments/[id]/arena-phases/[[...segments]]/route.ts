import { NextRequest } from "next/server";
import { proxyBackend } from "@/lib/backendProxy";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ id: string; segments?: string[] }> };
async function forward(request: NextRequest, { params }: Context) {
  const { id, segments = [] } = await params;
  if (!/^[1-9]\d*$/.test(id)) return Response.json({ detail: "Invalid tournament" }, { status: 422 });
  const path = segments.join("/");
  const allowed = request.method === "GET" ? (path === "" || path === "history") : request.method === "POST" ? path === "players" :
    request.method === "PUT" && (/^players\/[1-9]\d*\/(initial|best8|final)$/.test(path) || /^matches\/(64|32|16|8|4|2):[1-9]\d*$/.test(path));
  if (!allowed) return Response.json({ detail: "Unsupported phase API operation" }, { status: 404 });
  return proxyBackend(request, `/api/tournaments/${id}/arena-phases${path ? `/${path}` : ""}`);
}
export const GET = forward;
export const POST = forward;
export const PUT = forward;
