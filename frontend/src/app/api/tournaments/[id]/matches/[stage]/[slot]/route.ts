import { NextRequest } from "next/server";
import { proxyBackend } from "../../../../../../../lib/backendProxy";
import { parseChampionMatchSlot,parseChampionMatchStage,parsePositiveInteger } from "../../../../../../../lib/championProxyPolicy";
type Context={params:Promise<{id:string;stage:string;slot:string}>};
export async function PUT(request:NextRequest,{params}:Context){const{id,stage,slot}=await params;const tournamentId=parsePositiveInteger(id);const parsedStage=parseChampionMatchStage(stage);const parsedSlot=parsedStage?parseChampionMatchSlot(parsedStage,slot):null;if(tournamentId==null||parsedStage==null||parsedSlot==null)return Response.json({detail:"Invalid champion match slot"},{status:422});return proxyBackend(request,`/api/tournaments/${tournamentId}/matches/${parsedStage}/${parsedSlot}`);}
