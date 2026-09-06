import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
// @ts-expect-error Node's type-stripping test runner requires the extension.
import { matchEditorResultKey, normalizeChampionMatchAnalysis, normalizeFull64MatchAnalysis, selectMatchResultImage, validateMatchEditorResult } from "../src/lib/matchRegistration.ts";

const file = (name: string, size: number) => new File([new Uint8Array(size)], name, { type: "image/png" });

test("a usable modal crop is both the preview and the unchanged analysis upload", () => {
  const original = file("result.png", 100);
  const crop = file("result.match-modal.png", 60);
  const selected = selectMatchResultImage(original, { file: crop, preCropped: true });

  assert.equal(selected.originalFile, original);
  assert.equal(selected.previewFile, crop);
  assert.equal(selected.uploadFile, crop);
  assert.equal(selected.isModalCrop, true);
  assert.equal(selectMatchResultImage(original, { file: crop, preCropped: true }).previewFile, crop);
});

test("failed or oversized crops safely fall back to the original upload and preview", () => {
  const original = file("result.png", 100);
  for (const prepared of [
    { file: original, preCropped: false },
    { file: file("oversized.match-modal.png", 121), preCropped: true },
  ]) {
    const selected = selectMatchResultImage(original, prepared);
    assert.equal(selected.previewFile, original);
    assert.equal(selected.uploadFile, original);
    assert.equal(selected.isModalCrop, false);
  }
});

test("the shared editor owns stable URLs, stale-request guards, fallback, and responsive containment", () => {
  const editor = readFileSync(new URL("../src/components/MatchResultEditor.tsx", import.meta.url), "utf8");
  const full64 = readFileSync(new URL("../src/app/tournament/[id]/page.tsx", import.meta.url), "utf8");
  const champion = readFileSync(new URL("../src/components/ChampionTournamentRegistrationShell.tsx", import.meta.url), "utf8");

  assert.match(editor, /const generation=useRef\(0\)/);
  assert.match(editor, /if\(current!==generation\.current\)return/);
  assert.match(editor, /URL\.revokeObjectURL\(originalPreviewRef\.current\)/);
  assert.match(editor, /URL\.revokeObjectURL\(modalPreviewRef\.current\)/);
  assert.equal((editor.match(/URL\.createObjectURL/g) ?? []).length, 2);
  assert.match(editor, /setShowOriginal\(value=>!value\)/);
  assert.match(editor, /勝敗結果部分を切り出せなかったため、元画像を表示しています/);
  assert.match(editor, /max-w-full object-contain/);
  assert.match(editor, /min-w-0 overflow-hidden/);
  assert.match(editor, /preparedImage\.uploadFile/);
  assert.doesNotMatch(full64, /body\.append\("image",upload\)/);
  assert.doesNotMatch(champion, /body\.append\("image",upload\)/);
  assert.match(full64, /body\.append\("image",file\)/);
  assert.match(champion, /body\.append\("image",file\)/);
});

test("equivalent saved results have a stable key while a new analysis result changes it", () => {
  const savedA = { rounds: [
    { roundNumber: 1, winner: "left" as const },
    { roundNumber: 2, winner: "right" as const },
    { roundNumber: 3, winner: "left" as const },
    { roundNumber: 4, winner: "right" as const },
    { roundNumber: 5, winner: "left" as const },
  ], issues: [] };
  const sameAFromParentRerender = { rounds: [...savedA.rounds].reverse(), issues: [] };
  const analyzedB = { ...savedA, rounds: savedA.rounds.map(round => (
    round.roundNumber === 5 ? { ...round, winner: "right" as const } : round
  )) };

  assert.equal(matchEditorResultKey(savedA), matchEditorResultKey(sameAFromParentRerender));
  assert.notEqual(matchEditorResultKey(savedA), matchEditorResultKey(analyzedB));
});

test("full_64 and champion_8 normalization preserve recognized values and leave missing values unresolved", () => {
  const full64 = normalizeFull64MatchAnalysis({ rounds: [
    { round: 1, left: "WIN", right: "LOSE" },
    { round: 2, left: "?", right: "?" },
  ] });
  assert.deepEqual(full64.rounds.map(round => round.winner), ["left", null]);
  assert.match(validateMatchEditorResult(full64).join(" "), /ラウンド1～5|未判定/);

  const champion = normalizeChampionMatchAnalysis({ round_results: [
    { round_number: 1, winner_id: 10 },
    { round_number: 2, winner_id: null },
  ] }, 10, 20);
  assert.deepEqual(champion.rounds.map(round => round.winner), ["left", null]);
  assert.match(validateMatchEditorResult(champion).join(" "), /ラウンド1～5|未判定/);
});

test("the editor preserves saved state through analysis errors and blocks duplicate analysis posts", () => {
  const editor = readFileSync(new URL("../src/components/MatchResultEditor.tsx", import.meta.url), "utf8");

  assert.doesNotMatch(editor, /useEffect\(\(\)=>setResult\(initialResult\),\[initialResult\]\)/);
  assert.match(editor, /\[attacker\.id,defender\.id,initialResultKey\]/);
  assert.doesNotMatch(editor, /setResult\(null\)/);
  assert.match(editor, /if\(!preparedImage\|\|analysisInFlight\.current\)return/);
  assert.match(editor, /finally\{analysisInFlight\.current=false;\}/);
  assert.match(editor, /解析結果を反映しました。保存するまで確定されません。/);
});
