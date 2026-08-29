import assert from "node:assert/strict";
import test from "node:test";
// Node executes this TypeScript test directly via --experimental-strip-types.
// @ts-expect-error The explicit extension is required by that runtime mode.
import { formatMatchStageForDisplay, sortUniqueMatchStageDisplays } from "../src/lib/matchStageDisplay.ts";

test("formats champion-eight stage names from both raw and bracket fields", () => {
  for (const stage of ["QF1", "QF2", "QF3", "QF4"]) {
    assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: stage }), "ベスト8");
  }
  for (const stage of ["SF1", "SF2"]) {
    assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: stage }), "ベスト4");
  }
  assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: "Final" }), "FINAL");
  assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: "FINAL" }), "FINAL");
  assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: "raw", bracketStage: "quarterfinal", bracketSlot: 4 }), "ベスト8");
  assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: "raw", bracketStage: "semifinal", bracketSlot: 2 }), "ベスト4");
  assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: "raw", bracketStage: "final", bracketSlot: 1 }), "FINAL");
});

test("normalizes supported full-64 case and spacing variants", () => {
  for (const [stage, expected] of [
    ["BEST64", "ベスト64"], ["Best 64", "ベスト64"], ["best64", "ベスト64"],
    ["BEST32", "ベスト32"], ["Best 16", "ベスト16"], ["best8", "ベスト8"],
    ["BEST4", "ベスト4"], ["Final", "FINAL"], ["FINAL", "FINAL"],
  ]) {
    assert.equal(formatMatchStageForDisplay({ registrationScope: "full_64", rawStage: stage }), expected);
  }
  for (const stage of ["ベスト64", "ベスト32", "ベスト16", "ベスト8", "ベスト4"]) {
    assert.equal(formatMatchStageForDisplay({ registrationScope: "full_64", rawStage: stage }), stage);
  }
});

test("preserves unknown, invalid, and missing stages", () => {
  assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: "QF5" }), "QF5");
  assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: "unknown" }), "unknown");
  assert.equal(formatMatchStageForDisplay({ registrationScope: "champion_8", rawStage: null }), null);
  assert.equal(formatMatchStageForDisplay({ registrationScope: null, rawStage: "QF1" }), "QF1");
});

test("deduplicates mixed display stages and sorts them in tournament progression order", () => {
  assert.deepEqual(sortUniqueMatchStageDisplays([
    "ベスト8", "FINAL", "ベスト64", "ベスト8", "ベスト4", "ベスト32", "unknown", "ベスト16",
  ]), ["ベスト64", "ベスト32", "ベスト16", "ベスト8", "ベスト4", "FINAL", "unknown"]);
});
