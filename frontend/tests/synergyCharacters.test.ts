import assert from "node:assert/strict";
import test from "node:test";
// Node 24 executes this TypeScript test directly via --experimental-strip-types.
// @ts-expect-error The explicit extension is required by that runtime mode.
import { mapAndSortSynergyCharacters, shouldResetSynergySelection, teamMatchesSynergyConditions, transitionSynergySelection } from "../src/lib/synergyCharacters.ts";

test("sorts by count, then Japanese name, then character id and keeps zero-count characters last", () => {
  const characters = [
    { id: 8, name: "アニス" },
    { id: 3, name: "ラピ" },
    { id: 7, name: "アニス" },
    { id: 4, name: "ネオン" },
    { id: 5, name: "エマ" },
    { id: 6, name: "ディーゼル" },
  ];
  const usage = [
    { id: 3, count: 10, player_count: 1 },
    { id: 4, count: 9, player_count: 99 },
    { id: 8, count: 9, player_count: 2 },
    { id: 7, count: 9, player_count: 3 },
    { id: 5, count: 0, player_count: 100 },
  ];

  const sorted = mapAndSortSynergyCharacters(characters, usage);

  assert.deepEqual(sorted.map((item) => item.character.id), [3, 7, 8, 4, 5, 6]);
  assert.deepEqual(sorted.map((item) => item.count), [10, 9, 9, 9, 0, 0]);
  assert.deepEqual(sorted.map((item) => item.unavailable), [false, false, false, false, true, true]);
});

test("accepts character_id and deliberately ignores player_count for ordering", () => {
  const sorted = mapAndSortSynergyCharacters(
    [{ id: 1, name: "A" }, { id: 2, name: "B" }],
    [{ character_id: 1, count: 2, player_count: 1 }, { character_id: 2, count: 1, player_count: 50 }],
  );
  assert.deepEqual(sorted.map((item) => item.character.id), [1, 2]);
});

test("resets only when an initialized analysis key actually changes", () => {
  assert.equal(shouldResetSynergySelection(null, "scope-a"), false);
  assert.equal(shouldResetSynergySelection("scope-a", "scope-a"), false);
  assert.equal(shouldResetSynergySelection("scope-a", "scope-b"), true);
  assert.equal(shouldResetSynergySelection("scope-a", null), false);
});

test("cycles neutral to include to exclude to neutral without overlap", () => {
  const included = transitionSynergySelection(1, [], []);
  assert.deepEqual(included, { includedIds: [1], excludedIds: [] });

  const excluded = transitionSynergySelection(1, included.includedIds, included.excludedIds);
  assert.deepEqual(excluded, { includedIds: [], excludedIds: [1] });

  const neutral = transitionSynergySelection(1, excluded.includedIds, excluded.excludedIds);
  assert.deepEqual(neutral, { includedIds: [], excludedIds: [] });
});

test("uses the sixth neutral character as an exclusion and keeps exclusions unlimited", () => {
  const atLimit = transitionSynergySelection(6, [1, 2, 3, 4, 5], [7, 8]);
  assert.deepEqual(atLimit, {
    includedIds: [1, 2, 3, 4, 5],
    excludedIds: [7, 8, 6],
    addedAsExclusionDueToLimit: true,
  });
  const afterFreeingSlot = transitionSynergySelection(1, atLimit.includedIds, atLimit.excludedIds);
  assert.deepEqual(afterFreeingSlot.includedIds, [2, 3, 4, 5]);
  assert.deepEqual(afterFreeingSlot.excludedIds, [7, 8, 6, 1]);
});

test("does not select unavailable characters or the empty-slot id", () => {
  assert.deepEqual(transitionSynergySelection(10, [1], [2], false), { includedIds: [1], excludedIds: [2] });
  assert.deepEqual(transitionSynergySelection(9999, [1], [2]), { includedIds: [1], excludedIds: [2] });
});

test("matches every included character and none of the excluded characters", () => {
  assert.equal(teamMatchesSynergyConditions([5, 4, 3, 2, 1], [1, 3], []), true);
  assert.equal(teamMatchesSynergyConditions([1, 2, 3, 4, 5], [1, 3], [8, 9]), true);
  assert.equal(teamMatchesSynergyConditions([1, 2, 3, 4, 5], [1, 3], [5]), false);
  assert.equal(teamMatchesSynergyConditions([1, 1, 2, 3, 9999], [1, 2], [4]), true);
  assert.equal(teamMatchesSynergyConditions([1, 2, 3, 4, 5], [], [5]), false);
});
