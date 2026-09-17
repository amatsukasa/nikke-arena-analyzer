import assert from "node:assert/strict";
import test from "node:test";

import {
  groupSynergyCharacterOptions,
  mapAndSortSelectableSynergyCharacters,
  mapSynergyCharactersWithoutUsage,
  type ArenaCharacterDisplayMode,
  type SynergyCharacter,
} from "./synergyCharacters.ts";

const characters: SynergyCharacter[] = [
  { id: 1, name: "ナユタ", burst_phase: "1", is_arena_relevant: true },
  { id: 2, name: "アリーナキャラB", burst_phase: "1", is_arena_relevant: true },
  { id: 3, name: "アリーナキャラA", burst_phase: "1", is_arena_relevant: true },
  { id: 4, name: "アイギス", burst_phase: "1", is_arena_relevant: false },
  { id: 5, name: "通常エマ", burst_phase: "1", is_arena_relevant: false },
  { id: 6, name: "非アリーナキャラC", burst_phase: "1", is_arena_relevant: false },
  { id: 7, name: "採用なし", burst_phase: "1", is_arena_relevant: true },
];
const usage = characters.map((character) => ({
  character_id: character.id,
  count: character.id === 7 ? 0 : character.id,
}));

function namesFor(mode: ArenaCharacterDisplayMode): string[] {
  const options = mapAndSortSelectableSynergyCharacters(characters, usage, mode);
  return groupSynergyCharacterOptions(options, mode === "priority")
    .flatMap((group) => group.options.map((option) => option.character.name ?? ""));
}

test("arena priority keeps arena and non-arena groups in Japanese name order", () => {
  assert.deepEqual(namesFor("priority"), [
    "アリーナキャラA", "アリーナキャラB", "ナユタ",
    "アイギス", "通常エマ", "非アリーナキャラC",
  ]);
});

test("arena only excludes non-arena and zero-usage characters", () => {
  assert.deepEqual(namesFor("only"), ["アリーナキャラA", "アリーナキャラB", "ナユタ"]);
});

test("all ignores arena relevance and sorts every used character by name", () => {
  assert.deepEqual(namesFor("all"), [
    "アイギス", "アリーナキャラA", "アリーナキャラB",
    "ナユタ", "通常エマ", "非アリーナキャラC",
  ]);
});

test("burst group labels use fixed English notation", () => {
  const burstCharacters: SynergyCharacter[] = [
    { id: 11, burst_phase: "1" },
    { id: 12, burst_phase: "2" },
    { id: 13, burst_phase: "3" },
    { id: 14, burst_phase: "A" },
  ];
  const labels = groupSynergyCharacterOptions(
    burstCharacters.map((character) => ({ character, count: 1, unavailable: false })),
  ).map((group) => group.label);

  assert.deepEqual(labels, ["Burst: I", "Burst: II", "Burst: III", "Burst: A"]);
});

test("arena-only filtering can rely on Character metadata before usage loads", () => {
  const withEmpty = [...characters, { id: 9999, name: "空き枠", is_arena_relevant: true }];
  assert.deepEqual(
    mapSynergyCharactersWithoutUsage(withEmpty, "only").map((option) => option.character.id),
    [1, 2, 3, 7],
  );
  assert.equal(mapSynergyCharactersWithoutUsage(withEmpty, "all").length, characters.length);
});
