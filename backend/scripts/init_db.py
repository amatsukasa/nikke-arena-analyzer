import sys
import os
import csv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import Character

EMPTY_SLOT_CHARACTER_ID = 9999


def ensure_empty_slot_character(db):
    empty_slot = db.get(Character, EMPTY_SLOT_CHARACTER_ID)
    if empty_slot:
        if empty_slot.name not in ("空枠", "登録なし"):
            raise RuntimeError(f"ID {EMPTY_SLOT_CHARACTER_ID} は空枠以外のキャラクターに使用されています")
        empty_slot.name = "空枠"
        empty_slot.weapon = None
        empty_slot.element = None
        empty_slot.burst_phase = None
        empty_slot.manufacturer = None
        empty_slot.rarity = None
        empty_slot.class_type = None
        empty_slot.is_template_available = False
    else:
        name_conflict = db.query(Character).filter(Character.name == "空枠").first()
        if name_conflict:
            raise RuntimeError("「空枠」が予約ID以外で登録されています")
        db.add(Character(id=EMPTY_SLOT_CHARACTER_ID, name="空枠", is_template_available=False))
    db.commit()


def init_db():
    db = SessionLocal()
    
    # 既にデータベースにキャラクターが存在する場合はインポートをスキップ（管理画面での変更を保護）
    if db.query(Character).first() is not None:
        ensure_empty_slot_character(db)
        print("[Startup] すでにキャラクターデータが存在するため、初期CSVインポートをスキップします。")
        db.close()
        return

    csv_path = os.path.join(os.path.dirname(__file__), "characters.csv")
    
    if not os.path.exists(csv_path):
        print(f"CSV file not found at {csv_path}")
        db.close()
        return

    added_count = 0
    updated_count = 0
    
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            weapon = row.get("weapon", "").strip()
            element = row.get("element", "").strip()
            burst_phase = row.get("burst_phase", "").strip()
            manufacturer = row.get("manufacturer", "").strip()
            rarity = row.get("rarity", "").strip()
            class_type = row.get("class_type", "").strip()
            
            if not name:
                continue
                
            existing = db.query(Character).filter(Character.name == name).first()
            if existing:
                # Update existing character
                existing.weapon = weapon
                existing.element = element
                existing.burst_phase = burst_phase
                existing.manufacturer = manufacturer
                existing.rarity = rarity
                if class_type:
                    existing.class_type = class_type
                updated_count += 1
            else:
                # Add new character
                char = Character(
                    name=name,
                    weapon=weapon,
                    element=element,
                    burst_phase=burst_phase,
                    manufacturer=manufacturer,
                    rarity=rarity,
                    class_type=class_type if class_type else None
                )
                db.add(char)
                added_count += 1
                
    db.commit()
    ensure_empty_slot_character(db)
    db.close()
    print(f"Successfully added {added_count} and updated {updated_count} characters.")

if __name__ == "__main__":
    init_db()
