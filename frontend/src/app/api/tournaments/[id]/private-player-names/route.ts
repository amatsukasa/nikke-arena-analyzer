import { NextRequest } from "next/server";
import { proxyBackend } from "@/lib/backendProxy";
export const dynamic = "force-dynamic";
async function forward(request: NextRequest, {params}: {params: Promise<{id:string}>}) {
  const {id}=await params;
  if(!/^[1-9]\d*$/.test(id))return Response.json({detail:"Invalid tournament"},{status:422});
  const result=await proxyBackend(request, `/api/tournaments/${id}/private-player-names`);
  result.headers.set("Cache-Control","private, no-store");
  return result;
}
export const GET=forward;
export const PUT=forward;
