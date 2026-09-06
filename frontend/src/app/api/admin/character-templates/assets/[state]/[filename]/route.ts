import { NextRequest, NextResponse } from "next/server";
import { proxyBackend } from "../../../../../../../lib/backendProxy";

const ALLOWED_STATES = new Set(["active", "quarantine"]);
const TEMPLATE_FILENAME = /^char_\d+(?:_\d{3})?\.png$/;

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ state: string; filename: string }> },
) {
  const { state, filename } = await context.params;
  if (!ALLOWED_STATES.has(state) || !TEMPLATE_FILENAME.test(filename)) {
    return NextResponse.json({ detail: "Not Found" }, { status: 404 });
  }

  const response = await proxyBackend(
    request,
    `/api/admin/character-templates/assets/${state}/${encodeURIComponent(filename)}`,
  );
  if (response.ok) {
    // Generation filenames are immutable. A private cache prevents duplicate
    // downloads on this admin screen without making protected assets public.
    response.headers.set("Cache-Control", "private, max-age=60");
  }
  return response;
}
