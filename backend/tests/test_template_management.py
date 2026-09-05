import tempfile
import threading
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from services.collection_classifier import collection_match_mask
from services.template_management import (
    list_template_paths,
    move_to_quarantine,
    next_template_name,
    parse_template_name,
    reassign_active_template,
    representative_template,
    restore_from_quarantine,
    safe_template_path,
    template_operation_lock,
    template_sha256,
)
from services.template_matcher import TemplateCandidate, masked_absolute_similarity, masked_ccoef_normed, predict_character_match


class TemplateManagementPureTests(unittest.TestCase):
    def test_name_parsing_and_path_safety(self):
        self.assertEqual(parse_template_name("char_12.png").generation, 0)
        self.assertEqual(parse_template_name("char_12_003.png").generation, 3)
        for value in ("../char_12.png", "char_12_1.png", "CHAR_12.png", "char_12.png/evil"):
            with self.assertRaises(ValueError):
                parse_template_name(value)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                safe_template_path(Path(tmp), "char_12.png", 13)

    def test_symlink_is_not_listed_or_resolved_as_a_template(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            target = Path(outside) / "char_12.png"
            target.write_bytes(b"outside")
            link = root / "char_12.png"
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlinks are unavailable: {exc}")
            self.assertEqual(list_template_paths(root), [])
            with self.assertRaises(ValueError):
                safe_template_path(root, link.name, 12)

    def test_operation_lock_serializes_generation_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            upload_root = Path(tmp)
            active = upload_root / "templates"
            active.mkdir()
            allocated: list[str] = []
            inside = 0
            maximum_inside = 0
            state_lock = threading.Lock()

            def allocate() -> None:
                nonlocal inside, maximum_inside
                with template_operation_lock(upload_root):
                    with state_lock:
                        inside += 1
                        maximum_inside = max(maximum_inside, inside)
                    name = next_template_name(active, 12)
                    time.sleep(0.02)
                    (active / name).write_bytes(name.encode())
                    allocated.append(name)
                    with state_lock:
                        inside -= 1

            workers = [threading.Thread(target=allocate) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=2)
            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertEqual(maximum_inside, 1)
            self.assertEqual(sorted(allocated), ["char_12_001.png", "char_12_002.png"])

    def test_latest_active_and_quarantine_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "templates"; active.mkdir()
            (active / "char_7.png").write_bytes(b"zero")
            (active / "char_7_002.png").write_bytes(b"two")
            (active / "char_7_001.png").write_bytes(b"one")
            self.assertEqual(representative_template(active, 7).name, "char_7_002.png")
            _, quarantined = move_to_quarantine(root, 7, "char_7_002.png")
            self.assertEqual(representative_template(active, 7).name, "char_7_001.png")
            _, restored = restore_from_quarantine(root, 7, quarantined.name)
            self.assertEqual(restored.name, "char_7_002.png")
            self.assertEqual(representative_template(active, 7).name, "char_7_002.png")

    def test_reassign_avoids_duplicate_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); active = root / "templates"; active.mkdir()
            source = active / "char_1_001.png"; source.write_bytes(b"same")
            target = active / "char_2_001.png"; target.write_bytes(b"same")
            _, moved, duplicate = reassign_active_template(root, 1, 2, source.name)
            self.assertTrue(duplicate)
            self.assertEqual(template_sha256(target), template_sha256(moved))
            self.assertEqual(len([p for p in list_template_paths(active) if parse_template_name(p.name).character_id == 2]), 1)

    def test_collection_mask_excludes_roi_from_score_denominator(self):
        face = np.random.default_rng(7).integers(0, 256, (160, 160, 3), dtype=np.uint8)
        same_face_other_badge = face.copy()
        mask = collection_match_mask((160, 160))
        same_face_other_badge[mask == 0] = 255
        different_face_same_badge = np.random.default_rng(8).integers(0, 256, (160, 160, 3), dtype=np.uint8)
        different_face_same_badge[mask == 0] = face[mask == 0]
        match = predict_character_match(face, {
            1: [TemplateCandidate(same_face_other_badge, "char_1_001.png")],
            2: [TemplateCandidate(different_face_same_badge, "char_2_001.png")],
        }, threshold=0.0, min_margin=0.0)
        self.assertEqual(match.character_id, 1)
        self.assertEqual(match.matched_template_filename, "char_1_001.png")
        self.assertGreater(match.similarity, match.second_similarity)
        self.assertAlmostEqual(masked_ccoef_normed(face[:, :, 0], same_face_other_badge[:, :, 0], mask), 1.0)
        self.assertAlmostEqual(masked_absolute_similarity(face, same_face_other_badge, mask), 1.0)


if __name__ == "__main__":
    unittest.main()
