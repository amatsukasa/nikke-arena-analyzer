"use client";
import {useI18n} from "@/i18n/I18nProvider";
import {useCallback,useEffect,useState} from "react";
export type PrivatePlayerName={id:number;seed_number:number|null;champion_slot:number|null;private_name:string|null};
export function usePrivatePlayerNames(tournamentId:number){
  const {t}=useI18n();
  const [players,setPlayers]=useState<PrivatePlayerName[]>([]);
  const refresh=useCallback(async()=>{
    const response=await fetch(`/api/tournaments/${tournamentId}/private-player-names`,{cache:"no-store"});
    if(!response.ok)throw new Error("Private player names could not be loaded");
    setPlayers((await response.json()).players);
  },[tournamentId]);
  useEffect(()=>{setPlayers([]);if(Number.isInteger(tournamentId)&&tournamentId>0)void refresh().catch(()=>{});},[refresh,tournamentId]);
  const name=(player:{id?:number;seed_number?:number|null;seed?:number;champion_slot?:number|null})=>{
    const stored=players.find(p=>player.id?p.id===player.id:p.seed_number===(player.seed_number??player.seed));
    return stored?.private_name || t("privatePlayerName.defaultName",{seed:stored?.seed_number??player.seed_number??player.seed??""});
  };
  return {players,refresh,name};
}
