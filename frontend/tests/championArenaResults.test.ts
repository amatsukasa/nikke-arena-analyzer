import assert from "node:assert/strict";
import test from "node:test";
// @ts-expect-error Node test runtime requires the explicit extension.
import { calculateChampionArenaStats, loadUserData, type StoredArenaResult } from "../src/lib/championArenaResults.ts";

const tournaments=[
  {id:3,title:"Season 1",display_order:3,game_start_date:null},
  {id:2,title:"任意タイトル",display_order:2,game_start_date:null},
  {id:1,title:"過去大会",display_order:1,game_start_date:null},
];

test("distinguishes unknown, not participated, and latest participation",()=>{
  const stats=calculateChampionArenaStats(tournaments,{
    "3":{result:"not_participated",titleSnapshot:"Season 1"},
    "2":{result:"unknown",titleSnapshot:"任意タイトル"},
    "1":{result:"champion",titleSnapshot:"過去大会"},
  });
  assert.equal(stats.appearanceCount,2); assert.equal(stats.knownCount,1);
  assert.equal(stats.unknownCount,1); assert.equal(stats.bestResult,"champion");
  assert.equal(stats.latest?.tournament.id,2);
});

test("missing or corrupt storage safely returns empty data",()=>{
  assert.deepEqual(loadUserData({getItem:()=>null}),{version:1,championArena:{results:{}}});
  assert.deepEqual(loadUserData({getItem:()=>"broken"}),{version:1,championArena:{results:{}}});
});

test("orders explicit display order before null and uses date fallback",()=>{
  const ordered=[
    {id:1,title:"順序なし旧",display_order:null,game_start_date:"2025-01-01"},
    {id:2,title:"順序なし新",display_order:null,game_start_date:"2026-01-01"},
    {id:36,title:"Season 1",display_order:36,game_start_date:null},
    {id:37,title:"任意名称",display_order:37,game_start_date:null},
  ];
  const results:Record<string,StoredArenaResult>=Object.fromEntries(ordered.map(item=>[String(item.id),{result:"unknown",titleSnapshot:item.title}]));
  const stats=calculateChampionArenaStats(ordered,results);
  assert.equal(stats.latest?.tournament.id,37);
  results["37"].result="not_participated";
  results["36"].result="not_participated";
  assert.equal(calculateChampionArenaStats(ordered,results).latest?.tournament.id,2);
});
