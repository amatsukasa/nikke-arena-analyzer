import assert from "node:assert/strict";
import test from "node:test";
// @ts-expect-error Node's TypeScript strip mode requires the explicit extension.
import { playerIconUrl } from "../src/lib/playerIconUrl.ts";

test("player icon URL is stable until a successful write changes its revision", () => {
  const unchanged = Array.from({ length: 100 }, () =>
    playerIconUrl("/api/icon.png", 0),
  );
  assert.deepEqual(new Set(unchanged), new Set(["/api/icon.png"]));
  assert.equal(playerIconUrl("/api/icon.png", 12), "/api/icon.png?v=12");
  assert.equal(playerIconUrl("/api/icon.png?t=legacy", 12), "/api/icon.png?t=legacy");
  assert.equal(playerIconUrl(null, 12), null);
});
