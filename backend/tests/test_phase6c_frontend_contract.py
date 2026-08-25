"""Static contracts for Phase 6C's shared match-result frontend."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]

class Phase6CFrontendContractTest(unittest.TestCase):
    def read(self,path): return (ROOT/path).read_text(encoding="utf-8")

    def test_both_modes_use_shared_editor(self):
        full=self.read("frontend/src/app/tournament/[id]/page.tsx")
        champion=self.read("frontend/src/components/ChampionTournamentRegistrationShell.tsx")
        for source in (full,champion): self.assertIn("<MatchResultEditor",source)
        editor=self.read("frontend/src/components/MatchResultEditor.tsx")
        for contract in ("TeamDisplay","リザルト画像を選択","未判定","上書き","未保存の勝敗修正"):
            self.assertIn(contract,editor)

    def test_champion_proxy_validates_ids_stage_slot_and_methods(self):
        policy=self.read("frontend/src/lib/championProxyPolicy.ts")
        self.assertIn('value === "quarterfinal"',policy)
        self.assertIn('stage === "quarterfinal" ? 4 : stage === "semifinal" ? 2 : 1',policy)
        put=self.read("frontend/src/app/api/tournaments/[id]/matches/[stage]/[slot]/route.ts")
        analyze=self.read("frontend/src/app/api/tournaments/[id]/matches/[stage]/[slot]/analyze/route.ts")
        self.assertIn("export async function PUT",put)
        self.assertNotIn("export async function POST",put)
        self.assertIn("export async function POST",analyze)
        for source in (put,analyze):
            self.assertIn("parsePositiveInteger",source)
            self.assertIn("parseChampionMatchStage",source)
            self.assertIn("parseChampionMatchSlot",source)

    def test_champion_uses_backend_status_and_fixed_participants(self):
        shell=self.read("frontend/src/components/ChampionTournamentRegistrationShell.tsx")
        self.assertIn("selectedMatch.attacker.id",shell)
        self.assertIn("selectedMatch.defender.id",shell)
        self.assertIn('selectedMatch.status==="complete"',shell)
        self.assertIn("championDependentLabels",shell)
        self.assertNotIn("attacker_id:",shell)
        self.assertNotIn("defender_id:",shell)

    def test_pure_match_contract_has_seven_slots_and_majority(self):
        source=self.read("frontend/src/lib/matchRegistration.ts")
        self.assertEqual(source.count('["quarterfinal",'),4)
        self.assertEqual(source.count('["semifinal",'),2)
        self.assertEqual(source.count('["final",'),1)
        self.assertIn('rounds.length !== 5',source)
        self.assertIn('>= 3 ? "left" : "right"',source)

    def test_unresolved_select_is_normalized_to_null_and_blocks_save(self):
        editor=self.read("frontend/src/components/MatchResultEditor.tsx")
        contract=self.read("frontend/src/lib/matchRegistration.ts")
        self.assertIn('e.target.value==="left"||e.target.value==="right"?e.target.value:null',editor)
        self.assertGreaterEqual(contract.count('round.winner !== "left" && round.winner !== "right"'),2)
        self.assertIn('disabled={busy||issues.length>0||!winner}',editor)

    def test_publication_frontend_shows_champion_counts_and_structured_errors(self):
        manage=self.read("frontend/src/app/tournaments/manage/page.tsx")
        helper=self.read("frontend/src/lib/publication.ts")
        for value in ("counts.players", "counts.complete_players", "counts.teams", "counts.matches", "counts.round_results"):
            self.assertIn(value,helper)
        self.assertIn("error.code",helper)
        self.assertIn("error.message",helper)
        self.assertIn("publicationSummary(readiness)",manage)
        self.assertIn("publicationErrorLines(readiness)",manage)

    def test_adoption_display_uses_player_count_and_actual_denominator(self):
        helper=self.read("frontend/src/lib/adoptionRate.ts")
        self.assertIn("entry.adoption_rate",helper)
        self.assertIn("entry.player_count",helper)
        self.assertIn("totalRegisteredPlayers",helper)
        for path in ("frontend/src/app/page.tsx", "frontend/src/app/tournament/[id]/dashboard/page.tsx"):
            source=self.read(path)
            self.assertIn("adoptionDisplay(team, totalPlayers)",source)
            self.assertNotIn("const totalPlayers = 64",source)
            self.assertIn("登録データ内採用率",source)

    def test_mirror_matchup_history_expands_both_participation_sides(self):
        helper=self.read("frontend/src/lib/teamMatchupPerspective.ts")
        self.assertIn("attackerMatches",helper)
        self.assertIn("defenderMatches",helper)
        self.assertIn("...(attackerMatches ? [true] : [])",helper)
        self.assertIn("...(defenderMatches ? [false] : [])",helper)
        self.assertIn('${match.match_id}:${match.round_number}:${isAttacker ? "attacker" : "defender"}',helper)
        self.assertIn("match.attacker_player_id",helper)
        self.assertIn("match.defender_player_id",helper)
        for path in ("frontend/src/app/page.tsx", "frontend/src/app/tournament/[id]/dashboard/page.tsx"):
            source=self.read(path)
            self.assertIn("teamMatchupPerspective",source)
        history=self.read("frontend/src/components/TeamMatchupHistory.tsx")
        self.assertIn("match.participationKey",history)

    def test_cross_matchups_are_lazy_abortable_and_retryable(self):
        source=self.read("frontend/src/app/page.tsx")
        self.assertIn('if (activeTab !== "matchups") return;',source)
        self.assertNotIn('activeTab !== "matchups" && activeTab !== "team_winrate"',source)
        self.assertIn("new AbortController()",source)
        self.assertIn("signal: controller.signal",source)
        self.assertIn("setMatchups([])",source)
        self.assertIn("setMatchupsLoadedKey(\"\")",source)
        self.assertIn("setMatchupsRetry(value => value + 1)",source)
        self.assertIn('role="status"',source)
        self.assertIn('role="alert"',source)

if __name__=="__main__": unittest.main()
