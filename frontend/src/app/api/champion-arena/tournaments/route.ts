import { type NextRequest } from "next/server";
import { proxyBackend } from "@/lib/backendProxy";

export function GET(request: NextRequest) {
  return proxyBackend(request, "/api/champion-arena/tournaments");
}
