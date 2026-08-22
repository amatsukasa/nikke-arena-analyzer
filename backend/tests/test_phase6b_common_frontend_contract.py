"""Static contracts for the shared full_64/champion_8 Phase 6B frontend."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class Phase6BCommonFrontendContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / "frontend" / "src").is_dir():
            raise unittest.SkipTest("frontend source is not mounted in this backend-only test environment")

    def _read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_both_modes_use_the_same_deck_and_icon_components(self):
        full = self._read("frontend/src/app/tournament/[id]/page.tsx")
        champion = self._read("frontend/src/components/ChampionTournamentRegistrationShell.tsx")
        for source in (full, champion):
            self.assertIn("<DeckRegistrationEditor", source)
            self.assertIn("<PlayerIconEditor", source)
        self.assertNotIn('from "react-easy-crop"', full)
        self.assertNotIn("legacyPrepareAnalysisImageReference", full)

    def test_shared_editor_uses_common_search_preparation_validation_and_mobile_hook(self):
        editor = self._read("frontend/src/components/DeckRegistrationEditor.tsx")
        for contract in (
            "CharacterSearchSelect",
            "prepareAnalysisImage",
            "validateRegistrationTeams",
            "useMobileRoundAccordion",
            "getCharIconUrl",
        ):
            self.assertIn(contract, editor)
        self.assertIn('accept="image/jpeg,image/png,image/webp"', editor)
        self.assertIn('character.id===9999', editor)

    def test_player_crop_contract_is_shared_and_guards_double_submission(self):
        editor = self._read("frontend/src/components/PlayerIconEditor.tsx")
        for value in ('[1,"小 (1倍)"]', '[6,"中 (6倍)"]', '[10,"大 (10倍)"]'):
            self.assertIn(value, editor)
        self.assertIn("processing || busy", editor)
        self.assertIn('accept="image/jpeg,image/png,image/webp"', editor)
        self.assertIn('document.body.style.overflow = "hidden"', editor)
        self.assertIn('event.key === "Escape"', editor)

    def test_tournament_switch_resets_state_and_stale_loads_are_generation_guarded(self):
        shell = self._read("frontend/src/components/ChampionTournamentRegistrationShell.tsx")
        for reset in (
            "initialized.current=false",
            "setSlots(initialSlots())",
            "setSelectedSlot(1)",
            'setStep("seed")',
            "setTeams([])",
            "setDirty(false)",
            'setBusy("")',
            'setFormError("")',
        ):
            self.assertIn(reset, shell)
        self.assertIn("current===generation.current", shell)
        self.assertIn("controller.abort()", shell)
        self.assertIn("activeTournamentId.current!==operationTournament", shell)
        self.assertIn("key={`icon-${tournamentId}-${selected.player.id}`}", shell)
        self.assertIn("key={`decks-${tournamentId}-${selected.player.id}`}", shell)

    def test_bracket_player_and_registered_team_display_are_shared(self):
        full = self._read("frontend/src/app/tournament/[id]/page.tsx")
        champion_bracket = self._read("frontend/src/components/ChampionBracketTree.tsx")
        champion_shell = self._read("frontend/src/components/ChampionTournamentRegistrationShell.tsx")
        self.assertIn("<TournamentPlayerPill", full)
        self.assertIn("<TournamentPlayerPill", champion_bracket)
        self.assertIn("<DeckRegistrationViewer", full)
        self.assertIn("<DeckRegistrationViewer", champion_shell)
        viewer = self._read("frontend/src/components/DeckRegistrationViewer.tsx")
        self.assertIn("<TeamDisplay", viewer)
        self.assertIn('data-registration-mode="view"', viewer)
        self.assertIn("編成を修正", viewer)
        self.assertIn("<DeckRegistrationEditor", full)
        self.assertIn("<DeckRegistrationEditor", champion_shell)

    def test_completed_decks_open_in_view_mode_and_only_explicit_action_opens_editor(self):
        full = self._read("frontend/src/app/tournament/[id]/page.tsx")
        champion = self._read("frontend/src/components/ChampionTournamentRegistrationShell.tsx")
        self.assertIn('setDeckScreen(hasCompleteRegistrationStructure(savedTeams) ? "view" : "edit")', full)
        self.assertIn('registeredDecks.length > 0 && deckScreen === "view"', full)
        self.assertIn('onEditTeams={canEdit ? () => setDeckScreen("edit") : undefined}', full)
        self.assertIn("onEditPlayer={canEdit ? editFull64PlayerInfo : undefined}", full)
        self.assertIn('seedFieldRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })', full)
        self.assertNotIn("editFull64PlayerInfo", champion)
        self.assertIn('if (registeredDecks.length > 0) setDeckScreen("view")', full)
        self.assertIn("dirty={deckDirty}", full)
        self.assertIn("dirty={dirty}", champion)
        editor = self._read("frontend/src/components/DeckRegistrationEditor.tsx")
        self.assertIn('window.confirm("未保存の変更を破棄しますか？")', editor)
        self.assertIn('slot.teamStatus==="complete"?"summary":"player"', champion)
        self.assertIn('onEditTeams={canEdit&&!published?()=>setStep("decks"):undefined}', champion)
        self.assertIn('setStep("summary")', champion)

    def test_character_icon_urls_and_fallbacks_use_shared_contract(self):
        shared = self._read("frontend/src/utils/charIcon.ts")
        team = self._read("frontend/src/components/TeamDisplay.tsx")
        editor = self._read("frontend/src/components/DeckRegistrationEditor.tsx")
        self.assertIn("/api/char-icon/${id}.png", shared)
        self.assertIn("<CharacterIcon character={c}", team)
        self.assertIn("onError={() => setFailed(true)}", team)
        self.assertIn("getCharIconUrl", editor)
        self.assertNotIn("/api/char-icon/${character.id}`", editor)

    def test_proxy_has_safe_error_and_bounded_body(self):
        proxy = self._read("frontend/src/lib/backendProxy.ts")
        policy = self._read("frontend/src/lib/championProxyPolicy.ts")
        self.assertIn("CHAMPION_PROXY_MAX_BODY_BYTES", proxy)
        self.assertIn("readBoundedBody", proxy)
        self.assertIn("リクエスト容量が上限を超えています", proxy)
        self.assertIn("バックエンドへ接続できませんでした", proxy)
        self.assertNotIn("error.message", proxy)
        self.assertIn('incomingAuthorization?.startsWith("Bearer ")', proxy)
        self.assertNotIn('headers.set("Cookie"', proxy)
        self.assertNotIn('headers.set("Host"', proxy)
        self.assertIn('teams: new Set(["GET", "PUT"])', policy)
        self.assertIn('"analyze-deck": new Set(["POST"])', policy)
        self.assertIn('icon: new Set(["PUT", "DELETE"])', policy)
        self.assertIn("parsePositiveInteger", policy)
        self.assertIn("parseChampionSlot", policy)


if __name__ == "__main__":
    unittest.main()
