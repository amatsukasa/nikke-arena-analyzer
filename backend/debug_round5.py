"""
修正後のextract_match_resultsを全画像で実行して結果を検証する
"""
import sys
import os
import glob

# 本番コードをインポート
from services.match_processor import extract_match_results

if __name__ == "__main__":
    # 全トーナメントのmatch画像
    images = sorted(glob.glob("uploads/match_t*.png"))
    
    success = 0
    fail = 0
    
    for img_path in images:
        try:
            result = extract_match_results(img_path)
            fname = os.path.basename(img_path)
            
            # 各ラウンドが正しく左右逆になっているかチェック
            valid = True
            for r in result["rounds"]:
                if r["left"] == r["right"]:
                    valid = False
                    break
            
            rounds_str = " ".join([f"R{r['round']}:{r['left'][0]}/{r['right'][0]}" for r in result["rounds"]])
            status = "✅" if valid else "❌"
            winner_str = f"winner={result['winner']}"
            
            if not valid:
                print(f"{status} {fname}: {rounds_str} ({winner_str})")
                fail += 1
            else:
                success += 1
                
        except Exception as e:
            print(f"❌ {os.path.basename(img_path)}: ERROR - {e}")
            fail += 1
    
    print(f"\n=== 全画像テスト結果 ===")
    print(f"成功: {success}/{success+fail}")
    print(f"失敗: {fail}/{success+fail}")
    if fail == 0:
        print("🎉 全画像で正常に判定されました！")
