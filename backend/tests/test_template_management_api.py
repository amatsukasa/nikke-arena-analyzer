from datetime import date
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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
        result = main.list_character_templates(self.admin, self.db)
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
