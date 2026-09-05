from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class TemplateManagementFrontendContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / "frontend/src").is_dir():
            raise unittest.SkipTest("frontend source is not mounted")

    def test_admin_only_page_exposes_safe_operations(self):
        route = (ROOT / "frontend/src/app/admin/character-templates/page.tsx").read_text(encoding="utf-8")
        page = (ROOT / "frontend/src/components/admin/CharacterTemplatesAdmin.tsx").read_text(encoding="utf-8")
        admin = (ROOT / "frontend/src/app/admin/page.tsx").read_text(encoding="utf-8")
        for label in (
            "要確認",
            "Character別テンプレート",
            "無効化済み",
            "元のCharacterのまま維持",
            "修正先Characterへ移す",
            "どのCharacterにも使わず無効化",
            "正しいCharacterへ移す",
            "テンプレートとして無効化",
            "復元",
            "完全削除",
        ):
            self.assertIn(label, page)
        self.assertIn("同じ画像が既にある場合は重複登録しません", page)
        self.assertNotIn("要確認に記録されていない誤登録", page)
        self.assertIn("利用者による修正が誤りだった場合", page)
        self.assertIn("再び照合と代表画像の候補になります", page)
        self.assertIn('user?.role !== "admin"', page)
        self.assertEqual(page.count('"最終確認：完全削除しますか？"'), 1)
        self.assertIn("setActiveTab('templates')", admin)
        self.assertIn("<CharacterTemplatesAdmin embedded />", admin)
        self.assertNotIn("router.push('/admin/character-templates')", admin)
        self.assertNotIn("./character-templates/page", admin)
        self.assertIn("<CharacterTemplatesAdmin />", route)
        self.assertNotIn("export default function CharacterTemplatesAdmin(", route)
        self.assertIn('CharacterSearchSelect', page)
        self.assertIn('allowUnknown={false}', page)
        self.assertIn('allowEmpty={false}', page)
        self.assertIn('正しいCharacterを名前で検索', page)
        self.assertNotIn('window.prompt(', page)

        search = (ROOT / "frontend/src/components/CharacterSearchSelect.tsx").read_text(encoding="utf-8")
        self.assertIn("allowUnknown = true", search)
        self.assertIn("allowEmpty = true", search)
        self.assertIn("allowUnknown &&", search)
        self.assertIn("allowEmpty &&", search)

    def test_provenance_is_preserved_by_frontend_adapter(self):
        adapter = (ROOT / "frontend/src/lib/deckRegistration.ts").read_text(encoding="utf-8")
        for field in ("matched_template_filename", "similarity", "match_method", "analysis_token", "round_number", "position"):
            self.assertGreaterEqual(adapter.count(field), 3)


if __name__ == "__main__":
    unittest.main()
