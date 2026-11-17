"use client";
import {useEffect,useState} from "react";
// Candidate counts cover all registration stages; result rows remain stage-separated.
export function useTeamSearchUsage(enabled:boolean,ids:number[],singleId?:number){
 const [usage,setUsage]=useState<{id:number;count:number}[]>([]);
 const [state,setState]=useState<"loading"|"ready"|"error">("loading");
 const key=[...ids].sort((a,b)=>a-b).join(",");
 useEffect(()=>{
  if(!enabled)return;
  const controller=new AbortController();setState("loading");setUsage([]);
  if(!key){setState("ready");return()=>controller.abort();}
  async function load(){
   try{
    const response=await fetch(singleId?`/api/tournaments/${singleId}/dashboard/teams?registration_phase=all&limit=1000&min_matches=0`:"/api/dashboard/cross-tournament/stats",singleId?{signal:controller.signal,cache:"no-store"}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tournament_ids:key.split(",").map(Number),registration_phase:"all"}),signal:controller.signal});
    if(!response.ok)throw new Error("Search candidates unavailable");
    const data=await response.json();const counts=new Map<number,number>();
    if(singleId){for(const team of data.teams??[])for(const id of team.character_ids??[])counts.set(id,(counts.get(id)??0)+(team.count??0));}
    else{for(const section of Object.values(data.by_phase??{}) as any[])for(const char of section.character_usage??[])counts.set(char.id,(counts.get(char.id)??0)+(char.count??0));}
    if(!controller.signal.aborted){setUsage([...counts].map(([id,count])=>({id,count})));setState("ready");}
   }catch{if(!controller.signal.aborted)setState("error");}
  }void load();return()=>controller.abort();
 },[enabled,key,singleId]);
 return {usage,state};
}
