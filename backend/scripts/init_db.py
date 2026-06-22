import sys
import os
import csv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import Character

def init_db():
    db = SessionLocal()
    
    # 既にデータベースにキャラクターが存在する場合はインポートをスキップ（管理画面での変更を保護）
    if db.query(Character).first() is not None:
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
    db.close()
    print(f"Successfully added {added_count} and updated {updated_count} characters.")

if __name__ == "__main__":
    init_db()
