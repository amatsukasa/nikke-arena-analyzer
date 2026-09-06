import { NextRequest, NextResponse } from "next/server";
import { proxyBackend } from "../../../../lib/backendProxy";

const ALLOWED_FILTERS = new Set(["offset", "limit", "query", "rarity", "class_type"]);

export async function GET(request: NextRequest) {
  const incoming = request.nextUrl.searchParams;
  if ([...incoming.keys()].some((key) => !ALLOWED_FILTERS.has(key))) {
    return NextResponse.json({ detail: "Invalid query parameter" }, { status: 422 });
  }
  const offset = incoming.get("offset") ?? "0";
  const limit = incoming.get("limit") ?? "30";
  if (!/^\d+$/.test(offset) || !/^\d+$/.test(limit) || Number(limit) < 1 || Number(limit) > 100) {
    return NextResponse.json({ detail: "Invalid pagination" }, { status: 422 });
  }
  const outgoing = new URLSearchParams({ offset, limit });
  for (const key of ["query", "rarity", "class_type"]) {
    const value = incoming.get(key);
    if (value) outgoing.set(key, value);
  }
  return proxyBackend(request, `/api/admin/all-characters?${outgoing}`);
}
