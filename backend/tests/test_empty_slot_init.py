import unittest
import sys
from types import ModuleType
from unittest.mock import MagicMock


class FakeField:
    def __eq__(self, other):
        return ("eq", other)


class FakeCharacter:
    name = FakeField()

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


fake_database = ModuleType("database")
fake_database.SessionLocal = MagicMock()
fake_models = ModuleType("models")
fake_models.Character = FakeCharacter
sys.modules.setdefault("database", fake_database)
sys.modules.setdefault("models", fake_models)

from scripts.init_db import EMPTY_SLOT_CHARACTER_ID, ensure_empty_slot_character


class EmptySlotInitializationTests(unittest.TestCase):
    def test_creates_reserved_empty_slot_character(self):
        db = MagicMock()
        db.get.return_value = None
        db.query.return_value.filter.return_value.first.return_value = None

        ensure_empty_slot_character(db)

        added = db.add.call_args.args[0]
        self.assertEqual(added.id, EMPTY_SLOT_CHARACTER_ID)
        self.assertEqual(added.name, "空枠")
        self.assertFalse(added.is_template_available)
        db.commit.assert_called_once()

    def test_migrates_legacy_empty_slot_name(self):
        db = MagicMock()
        empty_slot = MagicMock()
        empty_slot.name = "登録なし"
        db.get.return_value = empty_slot

        ensure_empty_slot_character(db)

        self.assertEqual(empty_slot.name, "空枠")
        self.assertFalse(empty_slot.is_template_available)
        db.add.assert_not_called()
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
