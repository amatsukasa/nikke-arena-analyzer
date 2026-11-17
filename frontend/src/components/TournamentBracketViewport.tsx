"use client";
import {ReactNode,useLayoutEffect,useRef,useState} from "react";
import {useI18n} from "@/i18n/I18nProvider";

const BRACKET_BASE_WIDTH=960;

// Scale the complete coordinate space, including labels and connecting lines.
// Reserve its scaled height so the next section follows the visible bracket.
export default function TournamentBracketViewport({children}:{children:ReactNode}) {
 const {t}=useI18n();
 const viewport=useRef<HTMLDivElement>(null);
 const canvas=useRef<HTMLDivElement>(null);
 const [size,setSize]=useState({width:BRACKET_BASE_WIDTH,height:BRACKET_BASE_WIDTH});
 useLayoutEffect(()=>{
  const measure=()=>{
   if(!viewport.current||!canvas.current)return;
   const width=viewport.current.clientWidth;
   if(width<=0)return;
   const height=canvas.current.offsetHeight;
   setSize(previous=>previous.width===width&&previous.height===height?previous:{width,height});
  };
  const observer=new ResizeObserver(measure);
  if(viewport.current)observer.observe(viewport.current);
  if(canvas.current)observer.observe(canvas.current);
  measure();
  return()=>observer.disconnect();
 },[]);
 const scale=Math.min(1,size.width/BRACKET_BASE_WIDTH);
 return <div ref={viewport} role="region" aria-label={t("bracket.viewportLabel")} className="relative w-full min-w-0 overflow-hidden rounded-3xl" style={{height:Math.ceil(size.height*scale)}}>
  <div ref={canvas} style={{width:Math.max(BRACKET_BASE_WIDTH,size.width),transform:`scale(${scale})`,transformOrigin:"top left"}}>{children}</div>
 </div>;
}
