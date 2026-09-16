import os
import json
import time
from concurrent.futures import ThreadPoolExecutor

# 24場のコードおよび名称定義
STADIUM_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

def generate_single_stadium_json(code, date_str="20260916"):
    """
    指定された会場の個別 JSON（data_{code}.json または stadium_{code}.json）を生成する処理
    """
    file_name = f"stadium_{code}.json"
    
    # すでに本日のデータが存在している場合は無駄な処理をスキップして高速化
    if os.path.exists(file_name):
        try:
            with open(file_name, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("date") == date_str:
                    print(f" -> 既存最新ファイル読み込み完了: {file_name}")
                    return code, True
        except Exception:
            pass

    # 1場分のレースデータ構築（1R〜12R）
    races_data = {}
    for r in range(1, 13):
        races_data[str(r)] = {
            "weather": {
                "weather": "晴",
                "wind_speed": "2m",
                "wind_direction": "追い風",
                "wave": "2cm"
            },
            "summary_tag": "【本命濃厚】" if r % 2 == 1 else "【捲り一閃】",
            "racers": [
                {"name": "毒島 誠", "rank": "A1", "st": ".12", "tilt": "-0.5", "time": "6.65", "power": 92, "turn_offset": 20},
                {"name": "峰 竜太", "rank": "A1", "st": ".14", "tilt": "-0.5", "time": "6.68", "power": 85, "turn_offset": 35},
                {"name": "茅原 悠紀", "rank": "A1", "st": ".15", "tilt": "0.0", "time": "6.70", "power": 78, "turn_offset": 50},
                {"name": "馬場 貴也", "rank": "A1", "st": ".16", "tilt": "-0.5", "time": "6.72", "power": 70, "turn_offset": 65},
                {"name": "池田 浩二", "rank": "A1", "st": ".13", "tilt": "-0.5", "time": "6.67", "power": 88, "turn_offset": 40},
                {"name": "菊地 孝平", "rank": "A1", "st": ".17", "tilt": "0.0", "time": "6.74", "power": 65, "turn_offset": 80}
            ],
            "comment": "1号艇が絶好のスタートから1マークを先マイして独走態勢へ。2号艇と3号艇が鋭く差し込んで2着争いを展開する。",
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

    stadium_json_content = {
        "date": date_str,
        "stadium_code": code,
        "stadium_name": STADIUM_NAMES.get(code, "競艇場"),
        "races": races_data
    }

    # 各場個別の JSON ファイルとして書き出し保存
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(stadium_json_content, f, ensure_ascii=False, indent=2)

    print(f" -> 保存完了: {file_name}")
    return code, True

def main():
    start_time = time.time()
    today_str = "20260916"
    print(f"[{today_str} (JST)] 本日の開催場ごとに個別JSONデータを生成中...")

    # 本日の開催対象場（13場）
    active_codes = ["04", "05", "07", "08", "09", "11", "12", "13", "14", "18", "19", "22", "23"]

    # マルチスレッド並列処理（13場を同時に生成・出力して所要時間を大幅短縮）
    with ThreadPoolExecutor(max_workers=13) as executor:
        futures = [executor.submit(generate_single_stadium_json, code, today_str) for code in active_codes]
        for future in futures:
            future.result()

    elapsed = time.time() - start_time
    print(f"\n✅ 全開催場の個別JSON生成が完了しました。（所要時間: {elapsed:.2f}秒）")

if __name__ == "__main__":
    main()
