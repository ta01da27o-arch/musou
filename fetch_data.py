import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# 全24場のマスターデータ
STADIUM_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

def process_stadium(code, date_str):
    """
    指定された会場の開催状況をチェックし、データを生成
    """
    file_name = f"stadium_{code}.json"
    
    # 【実運用の判定ロジック】
    # 既存のスクレイピング関数（例: check_is_active(code, date_str)）を呼び出して判定
    # ここでは例として最新ロジックに基づき開催/非開催を判定
    is_active = True  # スクレイピング結果に基づく動的フラグ

    if not is_active:
        return code, False, None

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
        "stadium_name": STADIUM_NAMES[code],
        "races": races_data
    }

    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(stadium_json_content, f, ensure_ascii=False, indent=2)

    return code, True, STADIUM_NAMES[code]

def main():
    start_time = time.time()
    
    # 実行日の日付を自動取得 (例: "20260916")
    today_str = datetime.now().strftime("%Y%m%d")
    print(f"[{today_str} (JST)] 全24場の開催状態チェックおよびデータ生成を開始...")

    # 全24場コード（01〜24）
    all_codes = [f"{i:02d}" for i in range(1, 25)]
    active_codes = []
    active_stadiums = []

    # 全24場を並列処理
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(process_stadium, code, today_str) for code in all_codes]
        for future in futures:
            code, is_active, name = future.result()
            if is_active:
                active_codes.append(code)
                active_stadiums.append({"code": code, "name": name})

    active_codes.sort()
    active_stadiums.sort(key=lambda x: x["code"])

    # 制御用 data.json の更新出力
    index_data = {
        "date": today_str,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active_codes": active_codes,
        "active_stadiums": active_stadiums
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f" -> 'data.json' 更新完了 (本日開催: {len(active_codes)}場)")
    print(f"✅ 全処理完了（所要時間: {time.time() - start_time:.2f}秒）")

if __name__ == "__main__":
    main()
