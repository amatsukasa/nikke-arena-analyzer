from datetime import date
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from sqlalchemy import event

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402


class TemplateManagementApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.temp = tempfile.TemporaryDirectory()
        self.previous_upload_dir = main.UPLOAD_DIR
        main.UPLOAD_DIR = self.temp.name
        (Path(self.temp.name) / "templates").mkdir()
        self.admin = self.user("admin@example.invalid", "admin")
        self.user_row = self.user("user@example.invalid", "contributor")
        for character_id, name in ((1, "A"), (2, "B")):
            self.db.add(models.Character(id=character_id, name=name, rarity="SSR"))
        self.db.commit()
        (Path(self.temp.name) / "templates" / "char_1.png").write_bytes(b"legacy")
        (Path(self.temp.name) / "templates" / "char_1_001.png").write_bytes(b"new")

    def tearDown(self):
        self.db.close(); main.UPLOAD_DIR = self.previous_upload_dir; self.temp.cleanup()

    def user(self, email, role):
        row = models.AppUser(email=email, hashed_password="x", role=role, approval_status="active")
        self.db.add(row); self.db.flush(); return row

    def test_list_disable_restore_and_permanent_delete(self):
        result = main.list_character_templates(self.admin, self.db, "active", 0, 30, "")
        group = result["characters"][0]
        self.assertEqual([item["generation"] for item in group["active"]], [0, 1])
        self.assertTrue(group["active"][1]["representative"])
        main.disable_character_template(1, "char_1_001.png", {}, self.admin, self.db)
        self.assertFalse((Path(self.temp.name) / "templates" / "char_1_001.png").exists())
        self.assertTrue((Path(self.temp.name) / "template_quarantine" / "char_1_001.png").exists())
        main.restore_character_template(1, "char_1_001.png", self.admin, self.db)
        main.disable_character_template(1, "char_1_001.png", {}, self.admin, self.db)
        with self.assertRaises(HTTPException):
            main.permanently_delete_character_template(1, "char_1_001.png", "NO", self.admin, self.db)
        main.permanently_delete_character_template(1, "char_1_001.png", "DELETE", self.admin, self.db)
        self.assertFalse((Path(self.temp.name) / "template_quarantine" / "char_1_001.png").exists())
        self.assertEqual(self.db.query(models.CharacterTemplateAudit).count(), 4)

    def test_every_successful_admin_mutation_invalidates_matcher_cache(self):
        with patch.object(main, "_invalidate_template_matcher_cache") as invalidate:
            main.disable_character_template(1, "char_1_001.png", {}, self.admin, self.db)
            main.restore_character_template(1, "char_1_001.png", self.admin, self.db)
            main.disable_character_template(1, "char_1_001.png", {}, self.admin, self.db)
            main.permanently_delete_character_template(
                1, "char_1_001.png", "DELETE", self.admin, self.db
            )
        self.assertEqual(invalidate.call_count, 4)

    def test_template_listing_hashes_only_requested_page(self):
        root = Path(self.temp.name) / "templates"
        for generation in range(2, 37):
            (root / f"char_1_{generation:03d}.png").write_bytes(str(generation).encode())
        with patch.object(main, "describe_template", wraps=main.describe_template) as describe:
            result = main.list_character_templates(self.admin, self.db, "active", 0, 30, "")
        self.assertEqual(result["total"], 37)
        self.assertEqual(sum(len(group["active"]) for group in result["characters"]), 30)
        self.assertEqual(describe.call_count, 30)

    def test_admin_character_listing_is_filtered_paged_and_scans_templates_once(self):
        for character_id in range(3, 68):
            self.db.add(models.Character(
                id=character_id,
                name=f"Character {character_id:03d}",
                rarity="SSR" if character_id % 2 else "SR",
                class_type="火力型" if character_id % 3 else "支援型",
            ))
        self.db.commit()
        statements = []

        def record_sql(*args):
            statements.append(args[2])

        event.listen(engine, "before_cursor_execute", record_sql)
        try:
            with patch.object(main, "list_template_paths", wraps=main.list_template_paths) as listing:
                result = main.get_all_characters_admin(
                    self.admin, self.db, offset=0, limit=30,
                    query="Character", rarity="SSR", class_type="火力型",
                )
        finally:
            event.remove(engine, "before_cursor_execute", record_sql)

        self.assertLessEqual(len(result["characters"]), 30)
        self.assertEqual(result["offset"], 0)
        self.assertEqual(result["limit"], 30)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["has_next"], result["total"] > 30)
        self.assertTrue(all(row["rarity"] == "SSR" for row in result["characters"]))
        self.assertTrue(all(row["class_type"] == "火力型" for row in result["characters"]))
        self.assertEqual(listing.call_count, 1)
        select_statements = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
        self.assertEqual(len(select_statements), 2)

    def test_admin_character_listing_page_boundaries(self):
        self.db.query(models.Character).delete()
        self.db.commit()
        for total in (0, 1, 30, 31, 60, 61):
            with self.subTest(total=total):
                self.db.query(models.Character).delete()
                self.db.add_all([
                    models.Character(id=character_id, name=f"Character {character_id:03d}", rarity="SSR")
                    for character_id in range(1, total + 1)
                ])
                self.db.commit()

                first = main.get_all_characters_admin(
                    self.admin, self.db, offset=0, limit=30,
                    query="", rarity="", class_type="",
                )
                self.assertEqual(first["total"], total)
                self.assertEqual(len(first["characters"]), min(total, 30))
                self.assertEqual(first["page"], 1)
                self.assertEqual(first["has_next"], total > 30)

                if total > 30:
                    second = main.get_all_characters_admin(
                        self.admin, self.db, offset=30, limit=30,
                        query="", rarity="", class_type="",
                    )
                    self.assertEqual(second["total"], total)
                    self.assertEqual(len(second["characters"]), min(total - 30, 30))
                    self.assertEqual(second["page"], 2)
                    self.assertEqual(second["has_next"], total > 60)

                if total > 60:
                    third = main.get_all_characters_admin(
                        self.admin, self.db, offset=60, limit=30,
                        query="", rarity="", class_type="",
                    )
                    self.assertEqual(third["total"], total)
                    self.assertEqual(len(third["characters"]), total - 60)
                    self.assertEqual(third["page"], 3)
                    self.assertFalse(third["has_next"])

    def test_review_keep_does_not_move_predicted_template(self):
        tournament = models.Tournament(name="T", date=date(2026, 1, 1), created_by=self.user_row.id)
        self.db.add(tournament); self.db.flush()
        review = models.CharacterTemplateReview(
            predicted_character_id=1, corrected_character_id=2,
            matched_template_filename="char_1_001.png", corrected_template_filename=None,
            tournament_id=tournament.id, round_number=1, position=1,
            analysis_token="abcdef123456", match_method="masked_ccoeff_normed", created_by=self.user_row.id,
        )
        self.db.add(review); self.db.commit()
        main.resolve_character_template_review(review.id, {"action": "keep"}, self.admin, self.db)
        self.assertTrue((Path(self.temp.name) / "templates" / "char_1_001.png").exists())
        self.assertEqual(review.status, "kept")

    def test_admin_routes_are_registered_and_depend_on_backend_admin(self):
        expected = {
            ("/api/admin/character-templates", "GET"),
            ("/api/admin/character-template-reviews", "GET"),
            ("/api/admin/character-template-reviews/{review_id}/resolve", "POST"),
        }
        actual = {(route.path, method) for route in main.app.routes for method in getattr(route, "methods", set())}
        self.assertTrue(expected <= actual)

    def test_fresh_manual_correction_creates_one_pending_review_without_moving_a(self):
        tournament = models.Tournament(name="T", date=date(2026, 1, 1), created_by=self.user_row.id)
        self.db.add(tournament); self.db.flush()
        player = models.Player(tournament_id=tournament.id, seed_number=1, name="Player 1")
        self.db.add(player); self.db.flush()
        corrected = Path(self.temp.name) / "templates" / "char_2_001.png"
        corrected.write_bytes(b"corrected")
        crop = Path(self.temp.name) / "crop_t1_s1_abcdef123456_r1_c1.png"
        crop.write_bytes(b"crop")
        payload = {
            "id": 2, "original_predicted_id": 1,
            "matched_template_filename": "char_1_001.png",
            "similarity": 0.91, "match_method": "masked_ccoeff_normed",
            "analysis_token": "abcdef123456", "round_number": 1, "position": 1,
            "template_source_url": "/api/uploads/cropped/crop.png",
        }
        # The source filename contains the same tournament/seed/token issued by analysis.
        crop = crop.with_name(f"crop_t{tournament.id}_s1_abcdef123456_r1_c1.png")
        crop.write_bytes(b"crop")
        with patch.object(main, "path_from_upload_url", return_value=crop):
            for _ in range(2):
                main.add_template_correction_review(
                    self.db, payload=payload, corrected_template_filename=corrected.name,
                    tournament=tournament, player=player, actor=self.user_row,
                )
                self.db.flush()
        self.assertEqual(self.db.query(models.CharacterTemplateReview).count(), 1)
        self.assertTrue((Path(self.temp.name) / "templates" / "char_1_001.png").exists())

    def test_review_reassign_moves_only_matched_file_and_updates_both_metadata(self):
        tournament = models.Tournament(name="T", date=date(2026, 1, 1), created_by=self.user_row.id)
        self.db.add(tournament); self.db.flush()
        review = models.CharacterTemplateReview(
            predicted_character_id=1, corrected_character_id=2,
            matched_template_filename="char_1_001.png", corrected_template_filename=None,
            tournament_id=tournament.id, round_number=1, position=1,
            analysis_token="abcdef123456", match_method="masked_ccoeff_normed", created_by=self.user_row.id,
        )
        self.db.add(review); self.db.commit()
        result = main.resolve_character_template_review(review.id, {"action":"reassign","target_character_id":2}, self.admin, self.db)
        self.assertEqual(result["status"], "reassigned")
        self.assertTrue((Path(self.temp.name) / "templates" / result["target_filename"]).exists())
        self.assertTrue((Path(self.temp.name) / "templates" / "char_1.png").exists())
        self.assertFalse((Path(self.temp.name) / "templates" / "char_1_001.png").exists())
        self.assertEqual(self.db.get(models.Character, 1).template_filename, "char_1.png")
        self.assertEqual(self.db.get(models.Character, 2).template_filename, result["target_filename"])

    def test_disable_commit_failure_restores_file(self):
        path = Path(self.temp.name) / "templates" / "char_1_001.png"
        with patch.object(self.db, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaises(RuntimeError):
                main.disable_character_template(1, path.name, {}, self.admin, self.db)
        self.assertTrue(path.exists())
        self.assertFalse((Path(self.temp.name) / "template_quarantine" / path.name).exists())


if __name__ == "__main__":
    unittest.main()
