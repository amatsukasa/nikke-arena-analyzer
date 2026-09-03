import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
// @ts-expect-error Node's type-stripping test runner requires the extension.
import { normalizeAnalyzedRegistrationTeams, normalizeSavedRegistrationTeams, registrationCharacterImageUrl } from "../src/lib/deckRegistration.ts";
// @ts-expect-error Node's type-stripping test runner requires the extension.
import { createInitialPlayerIconCropSettings } from "../src/lib/playerIconCrop.ts";
// @ts-expect-error Node's type-stripping test runner requires the extension.
import { getCharIconUrl } from "../src/utils/charIcon.ts";

test("full_64 analysis accepts numeric and numeric-string Character IDs", () => {
  const teams = normalizeAnalyzedRegistrationTeams({
    suggested_teams: [[
      { predicted_character_id: 101, image_url: "/api/uploads/cropped/101.webp" },
      { predicted_character_id: "102", image_url: "/api/uploads/cropped/102.webp" },
      { predicted_character_id: "9999" },
      { predicted_character_id: null },
      { predicted_character_id: "not-an-id" },
    ]],
  });

  assert.deepEqual(teams[0].characters.map(character => character.id), [101, 102, 9999, null, null]);
  assert.equal(teams[0].characters[0].image_url, "/api/uploads/cropped/101.webp");
  assert.equal(teams[0].characters[1].image_url, "/api/uploads/cropped/102.webp");
  assert.equal(teams[0].characters[2].collection_level, null);
});

test("structured champion_8 and saved responses retain the same ID compatibility", () => {
  const analyzed = normalizeAnalyzedRegistrationTeams({
    teams: [{ team_number: 1, characters: [
      { character_id: "201", unresolved: false },
      { character_id: 202, unresolved: false },
    ] }],
  });
  const saved = normalizeSavedRegistrationTeams({
    decks: [{ team_number: 1, character_ids: ["201", 202, "9999"] }],
  });

  assert.deepEqual(analyzed[0].characters.map(character => character.id), [201, 202]);
  assert.deepEqual(saved[0].characters.map(character => character.id), [201, 202, 9999]);
});

test("analysis crop, explicit icon, and template fallback resolve in safe priority order", () => {
  assert.equal(
    registrationCharacterImageUrl(
      { id: 1, collection_level: "none", preview_image_data_url: "data:image/webp;base64,preview", image_url: "/crop.png" },
      { id: 1, icon_url: "/icon.png", is_template_available: true },
    ),
    "data:image/webp;base64,preview",
  );
  assert.equal(
    registrationCharacterImageUrl(
      { id: 2, collection_level: "none", image_url: "/api/uploads/cropped/2.webp" },
      { id: 2, is_template_available: true },
    ),
    "/api/uploads/cropped/2.webp",
  );
  assert.equal(
    registrationCharacterImageUrl(
      { id: 3, collection_level: "none" },
      { id: 3, is_template_available: true },
    ),
    "/api/char-icon/3.png",
  );
  assert.equal(registrationCharacterImageUrl({ id: 9999, collection_level: null }), "");
  assert.equal(registrationCharacterImageUrl({ id: 404, collection_level: "none" }), "");
});

test("saved-deck icons use file-backed Character metadata without speculative requests", () => {
  assert.equal(
    getCharIconUrl({ id: 24, icon_url: "/api/char-icon/24.png", is_template_available: true }),
    "/api/char-icon/24.png",
  );
  assert.equal(
    getCharIconUrl({ id: "34", is_template_available: true, template_filename: "char_34_001.png" }),
    "/api/char-icon/34.png",
  );
  assert.equal(getCharIconUrl({ id: 404, is_template_available: false }), "");
  assert.equal(getCharIconUrl({ id: 9999, is_template_available: false }), "");
});

test("both modes own one shared crop session while the editor keeps image state transient", () => {
  const initial = createInitialPlayerIconCropSettings();
  const changed = { crop: { x: 18, y: -27 }, zoom: 6 };
  assert.deepEqual(initial, { crop: { x: 0, y: 0 }, zoom: 1 });
  assert.deepEqual(changed, { crop: { x: 18, y: -27 }, zoom: 6 });
  assert.equal("source" in changed, false);
  assert.equal("playerId" in changed, false);

  const full64 = readFileSync(new URL("../src/app/tournament/[id]/page.tsx", import.meta.url), "utf8");
  const champion = readFileSync(new URL("../src/components/ChampionTournamentRegistrationShell.tsx", import.meta.url), "utf8");
  const editor = readFileSync(new URL("../src/components/PlayerIconEditor.tsx", import.meta.url), "utf8");
  for (const source of [full64, champion]) {
    assert.match(source, /usePlayerIconCropSettings\(\)/);
    assert.match(source, /cropSettings=\{playerIconCropSettings\}/);
  }
  assert.match(editor, /const \[source, setSource\] = useState/);
  assert.doesNotMatch(editor, /setZoom\(1\)/);
  assert.doesNotMatch(editor, /setCrop\(\{ x: 0, y: 0 \}\)/);
});

test("both registration modes refresh the shared Character catalog after saving", () => {
  const full64 = readFileSync(new URL("../src/app/tournament/[id]/page.tsx", import.meta.url), "utf8");
  const champion = readFileSync(new URL("../src/components/ChampionTournamentRegistrationShell.tsx", import.meta.url), "utf8");
  const hook = readFileSync(new URL("../src/hooks/useCharacterCatalog.ts", import.meta.url), "utf8");

  for (const source of [full64, champion]) {
    assert.match(source, /useCharacterCatalog/);
    assert.match(source, /await refreshCharacters\(\)/);
    assert.doesNotMatch(source, /window\.location\.reload/);
  }
  assert.match(hook, /cache: "no-store"/);
  assert.match(hook, /new AbortController\(\)/);
  assert.match(hook, /current !== generation\.current/);
  assert.doesNotMatch(hook, /setCharacters\(\[\]\)/);
});
