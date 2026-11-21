import { NextRequest, NextResponse } from "next/server";
import { articleIdPattern } from "@/lib/articles";
import { proxyBackend } from "@/lib/backendProxy";

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const [section, id] = path;
  const valid = path.length === 1 && (section === "guides" || articleIdPattern.test(section))
    || path.length === 2 && (section === "season" && /^\d+$/.test(id) || section === "images" && articleIdPattern.test(id));
  if (!valid) return new NextResponse(null, { status: 404 });
  return proxyBackend(request, `/api/articles/${path.join("/")}`);
}
