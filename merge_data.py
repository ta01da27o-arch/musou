import glob
import json
import os

def merge_stadium_files():
    files = glob.glob("stadium_*.json")
    if not files:
        print("stadium_*.json ファイルが見つかりません。")
        return

    all_data = {}
    active_codes = []

    for filepath in sorted(files):
        filename = os.path.basename(filepath)
        code = filename.replace("stadium_", "").replace(".json", "")
        active_codes.append(code)
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                all_data[code] = json.load(f)
            print(f"統合追加: {filename} (コード: {code})")
        except Exception as e:
            print(f"読み込みエラー {filename}: {e}")

    output_data = {
        "date": "20260916",
        "active_codes": active_codes,
        "stadiums": all_data
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 統合完了！ 'data.json' を生成しました。(収録場数: {len(active_codes)}場)")

if __name__ == "__main__":
    merge_stadium_files()
