import assert from "node:assert/strict";
import test from "node:test";
// Node executes this TypeScript test directly via --experimental-strip-types.
// @ts-expect-error The explicit extension is required by that runtime mode.
import { groupOpponentMatchups, matchupSideResults, teamMatchupPerspective } from "../src/lib/teamMatchupPerspective.ts";

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

test("keeps scoped opponent totals when only some rounds are visible", () => {
  const opponentA = "1,2,3,4,5";
  const opponentB = "6,7,8,9,10";
  const opponentC = "11,12,13,14,15";
  const attackWin = { opponentCanonical: opponentA, isWin: true, opponent: [1, 2, 3, 4, 5] };
  const defenseLoss = { opponentCanonical: opponentA, isWin: false, opponent: [5, 4, 3, 2, 1] };
  const otherWin = { opponentCanonical: opponentB, isWin: true, opponent: [6, 7, 8, 9, 10] };
  const otherLoss = { opponentCanonical: opponentC, isWin: false, opponent: [11, 12, 13, 14, 15] };
  const scoped = [attackWin, otherWin, otherLoss, defenseLoss];

  const all = groupOpponentMatchups(scoped, scoped);
  assert.deepEqual([...all.keys()], [opponentA, opponentB, opponentC]);
  assert.deepEqual(all.get(opponentA), { rows: [attackWin, defenseLoss], wins: 1, losses: 1 });
  assert.deepEqual(all.get(opponentB), { rows: [otherWin], wins: 1, losses: 0 });

  const losses = groupOpponentMatchups(scoped, [otherLoss, defenseLoss]);
  assert.deepEqual([...losses.keys()], [opponentC, opponentA]);
  assert.deepEqual(losses.get(opponentA), { rows: [defenseLoss], wins: 1, losses: 1 });
  assert.deepEqual(groupOpponentMatchups([defenseLoss], [defenseLoss]).get(opponentA),
    { rows: [defenseLoss], wins: 0, losses: 1 });
  assert.equal(groupOpponentMatchups(scoped, []).size, 0);
});
