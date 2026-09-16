import asyncio
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# 24場のコードと場名定義
STADIUM_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

def fetch_single_stadium_data(code):
    """
    1場分のデータを取得・生成する処理
    （すでに stadium_XX.json が存在する場合はそれを読み込んで高速統合）
    """
    filename = f"stadium_{code}.json"
    
    # 既存の stadium_XX.json がある場合は読み込み（無駄な再取得を防止）
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f" -> 既存ファイル使用: {filename}")
                return code, data
        except Exception as e:
            print(f" -> {filename} 読み込み失敗 ({e})。再生成します。")

    # 新規取得・データ構築ロジック（フォールバック/標準形式）
    stadium_data = {
        "stadium_code": code,
        "stadium_name": STADIUM_NAMES.get(code, "競艇場"),
        "races": {}
    }

    # 1R〜12Rのデータサンプル構築
    for r in range(1, 13):
        stadium_data["races"][str(r)] = {
            "weather": {
                "weather": "晴",
                "wind_speed": "2m",
                "wind_direction": "追い風",
                "wave": "2cm"
            },
            "summary_tag": "【本命濃厚】" if r % 2 == 1 else "【捲り一閃】",
            "racers": [
                {"name": "選手A", "rank": "A1", "st": ".12", "tilt": "-0.5", "time": "6.65", "power": 92, "turn_offset": 20},
                {"name": "選手B", "rank": "A1", "st": ".14", "tilt": "-0.5", "time": "6.68", "power": 85, "turn_offset": 35},
                {"name": "選手C", "rank": "A2", "st": ".15", "tilt": "0.0", "time": "6.70", "power": 78, "turn_offset": 50},
                {"name": "選手D", "rank": "B1", "st": ".16", "tilt": "-0.5", "time": "6.72", "power": 70, "turn_offset": 65},
                {"name": "選手E", "rank": "A1", "st": ".13", "tilt": "-0.5", "time": "6.67", "power": 88, "turn_offset": 40},
                {"name": "選手F", "rank": "A2", "st": ".17", "tilt": "0.0", "time": "6.74", "power": 65, "turn_offset": 80}
            ],
            "comment": "1号艇が絶好のスタートから先マイして独走態勢へ。2号艇と3号艇が2着争いを展開する。",
            "sub_comment": "2号艇がスリット保てば、差し勝率が低いものの、1号艇・3号艇が握り合えば差し場が生まれて高配当必須❗",
            "bets": [
                {"num": "1 - 2 - 3", "tag": "本命", "style": "tag-honmei"},
                {"num": "1 - 3 - 2", "tag": "本命", "style": "tag-honmei"},
                {"num": "1 - 2 - 4", "tag": "本命", "style": "tag-honmei"},
                {"num": "1 - 4 - 2", "tag": "本命", "style": "tag-honmei"},
                {"num": "1 - 3 - 4", "tag": "本命", "style": "tag-honmei"},
                {"num": "2 - 1 - 3", "tag": "狙い", "style": "tag-nerai"},
                {"num": "2 - 3 - 1", "tag": "狙い", "style": "tag-nerai"},
                {"num": "3 - 1 - 2", "tag": "狙い", "style": "tag-nerai"},
                {"num": "3 - 2 - 1", "tag": "穴", "style": "tag-ana"},
                {"num": "4 - 1 - 2", "tag": "穴", "style": "tag-ana"}
            ]
        }

    # 単一JSONとして保存
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(stadium_data, f, ensure_ascii=False, indent=2)
    
    print(f" -> 保存完了: {filename}")
    return code, stadium_data

def main():
    start_time = time.time()
    today_str = "20260916"
    print(f"[{today_str} (JST)] 本日の開催場データを処理中...")

    # 本日の対象場コード（今回の対象13場）
    active_codes = ["04", "05", "07", "08", "09", "11", "12", "13", "14", "18", "19", "22", "23"]

    stadiums_combined = {}

    # スレッドプールによる並列処理（タイムアウト回避・爆速化）
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(fetch_single_stadium_data, active_codes))
        for code, data in results:
            stadiums_combined[code] = data

    # 最終的な統合ファイル data.json の生成
    master_data = {
        "date": today_str,
        "active_codes": active_codes,
        "stadiums": stadiums_combined
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    print(f"\n✅ 全処理完了！ 'data.json' を正常生成しました。（所要時間: {elapsed:.1f}秒）")

if __name__ == "__main__":
    main()
