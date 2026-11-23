import assert from "node:assert/strict";
import test from "node:test";
import {
  calculateChampionArenaStats, CHAMPION_ARENA_STORAGE_KEY, emptyUserData,
  LEGACY_ARENA_STORAGE_KEY, loadUserData, resolveArenaEntries, saveArenaResult,
  type ArenaResult, type ArenaTournament, type UserDataV1,
// @ts-expect-error Node test runtime requires the explicit extension.
} from "../src/lib/championArenaResults.ts";

const newest: ArenaTournament = { id: "championship:3", title: "Newest", display_order: 42 };
const event: ArenaTournament = { id: "championship:1", title: "Title", display_order: 37, legacy_tournament_ids: [94, 123] };
const unlinked: ArenaTournament = { id: "legacy-tournament:94", title: "Title", display_order: 1, source: "legacy_tournament", tournament_id: 94 };
const record = (result: ArenaResult) => ({ result, titleSnapshot: "Previous label" });
const data = (results: UserDataV1["championArena"]["results"] = {}): UserDataV1 => ({
  version: 1, championArena: { results },
});

test("uses explicit IDs from both historical stores and counts each event once", () => {
  const current = data({ "legacy-tournament:94": record("unknown"), "championship:1": record("unknown") });
  const old = data({ "94": record("unknown"), "123": record("unknown"), "1": record("champion") });
  const entries = resolveArenaEntries([newest, event], current, old);
  const stats = calculateChampionArenaStats(entries);
  assert.equal(stats.appearanceCount, 1);
  assert.equal(stats.knownCount, 0);
  assert.equal(stats.unknownCount, 1);
  assert.equal(stats.latest?.tournament.id, event.id);
  assert.equal(resolveArenaEntries([{ ...event, legacy_tournament_ids: [] }], data(), old)[0].result, "not_entered");
  assert.equal(resolveArenaEntries([event], data({ "legacy-tournament:94": record("best32") }), data())[0].result, "best32");
  assert.equal(resolveArenaEntries([unlinked], data(), old)[0].result, "unknown");
});

test("uses the same server order for latest, skips unset and keeps explicit non-participation", () => {
  const current = data({ [newest.id]: record("not_participated"), [event.id]: record("runner_up") });
  const stats = calculateChampionArenaStats(resolveArenaEntries([newest, event], current, data()));
  assert.equal(stats.appearanceCount, 1);
  assert.equal(stats.knownCount, 1);
  assert.equal(stats.bestResult, "runner_up");
  assert.equal(stats.latest?.tournament.id, newest.id);
});

test("conflicts preserve all inputs until a choice and a saved clear cannot revive old values", () => {
  const old = data({ "94": record("best32") });
  const current = data({ "legacy-tournament:94": record("league_loss"), [event.id]: record("best8") });
  const values = new Map([[LEGACY_ARENA_STORAGE_KEY, JSON.stringify(old)], [CHAMPION_ARENA_STORAGE_KEY, JSON.stringify(current)]]);
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value) };
  const entry = resolveArenaEntries([event], current, old)[0];
  assert.deepEqual(new Set(entry.conflicts), new Set(["best8", "league_loss", "best32"]));
  assert.equal(calculateChampionArenaStats([entry]).appearanceCount, 0);
  saveArenaResult(storage, entry, "not_entered");
  const saved = loadUserData(storage);
  assert.equal(resolveArenaEntries([event], saved, loadUserData(storage, LEGACY_ARENA_STORAGE_KEY))[0].result, "not_entered");
  assert.deepEqual(saved.championArena.results["legacy-tournament:94"], current.championArena.results["legacy-tournament:94"]);
  assert.equal(values.get(LEGACY_ARENA_STORAGE_KEY), JSON.stringify(old));
  assert.equal(resolveArenaEntries([unlinked], data({ [unlinked.id]: record("not_entered") }), old)[0].result, "not_entered");
  assert.equal(resolveArenaEntries([event], data({ [unlinked.id]: record("not_entered") }), old)[0].result, "not_entered");
});

test("missing or malformed stores safely return empty data", () => {
  for (const value of [null, "broken", '{"version":1,"championArena":{"results":[]}}']) {
    assert.deepEqual(loadUserData({ getItem: () => value }), emptyUserData());
  }
});
