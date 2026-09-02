import assert from "node:assert/strict";
import test from "node:test";
// Node executes this TypeScript test directly via --experimental-strip-types.
// @ts-expect-error The explicit extension is required by that runtime mode.
import { matchupSideResults, teamMatchupPerspective } from "../src/lib/teamMatchupPerspective.ts";

test("maps attacker and defender wins for all four analysis perspectives", () => {
  assert.deepEqual(matchupSideResults({ winner_is_attacker: true, isAttacker: true, isWin: true }), { attacker: "WIN", defender: "LOSE" });
  assert.deepEqual(matchupSideResults({ winner_is_attacker: false, isAttacker: true, isWin: false }), { attacker: "LOSE", defender: "WIN" });
  assert.deepEqual(matchupSideResults({ winner_is_attacker: false, isAttacker: false, isWin: true }), { attacker: "LOSE", defender: "WIN" });
  assert.deepEqual(matchupSideResults({ winner_is_attacker: true, isAttacker: false, isWin: false }), { attacker: "WIN", defender: "LOSE" });
});

test("falls back to the analysis perspective when older data omits winner side", () => {
  assert.deepEqual(matchupSideResults({ isAttacker: true, isWin: true }), { attacker: "WIN", defender: "LOSE" });
  assert.deepEqual(matchupSideResults({ isAttacker: false, isWin: true }), { attacker: "LOSE", defender: "WIN" });
});

test("keeps both full64 and champion mirror participations with unique React keys", () => {
  for (const stage of ["BEST8", "QF1"]) {
    const mirror = {
      match_id: stage === "BEST8" ? 64 : 8,
      round_number: 3,
      stage,
      canonical_attacker: "1-2-3-4-5",
      canonical_defender: "1-2-3-4-5",
      attacker_team: [1, 2, 3, 4, 5],
      defender_team: [1, 2, 3, 4, 5],
      attacker_player_id: 101,
      defender_player_id: 202,
      attacker_team_id: 1001,
      defender_team_id: 2002,
      winner_is_attacker: true,
    };
    const result = teamMatchupPerspective([mirror], "1-2-3-4-5", (value) => String(value));
    assert.equal(result.details.length, 2);
    assert.deepEqual(result.details.map((entry) => entry.isAttacker), [true, false]);
    assert.deepEqual(result.details.map((entry) => entry.isWin), [true, false]);
    assert.equal(new Set(result.details.map((entry) => entry.participationKey)).size, 2);
    assert.deepEqual(result.details.map((entry) => entry.playerId), [101, 202]);
  }
});
