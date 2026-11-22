import { NextRequest, NextResponse } from "next/server";
import { articleIdPattern } from "@/lib/articles";
import { proxyBackend } from "@/lib/backendProxy";

type Context = { params: Promise<{ path?: string[] }> };

async function handle(request: NextRequest, { params }: Context) {
  const { path = [] } = await params;
  const [id] = path;
  const valid = path.length === 0 && request.method !== "PUT"
    || path.length === 1 && (request.method === "POST" ? id === "images" : articleIdPattern.test(id));
  if (!valid) return new NextResponse(null, { status: 404 });
  return proxyBackend(request, `/api/admin/articles${id ? `/${id}` : ""}`);
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
