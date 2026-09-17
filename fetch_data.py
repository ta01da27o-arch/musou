import os
import json
import time
import re
import urllib.request
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

STADIUM_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.boatrace.jp/"
}

def get_active_stadiums_today(date_str):
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    req = urllib.request.Request(url, headers=HEADERS)
    active_codes = []
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            
            links = soup.select('a[href*="jcd="]')
            for link in links:
                href = link.get("href", "")
                m = re.search(r"jcd=(\d{2})", href)
                if m:
                    jcd = m.group(1)
                    if jcd in STADIUM_NAMES and jcd not in active_codes:
                        active_codes.append(jcd)
    except Exception as e:
        print(f"開催一覧取得エラー: {e}")
        
    return sorted(active_codes)

def fetch_race_racers(jcd, rno, date_str):
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd}&hd={date_str}"
    req = urllib.request.Request(url, headers=HEADERS)
    racers = []
    
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            html = response.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            
            # 登番リンクを含むアンカータグから選手名を抽出
            name_anchors = soup.find_all("a", href=re.compile(r"toban=\d+"))
            for a in name_anchors:
                name = a.text.strip().replace("\u3000", " ")
                if name and not any(r["name"] == name for r in racers):
                    racers.append({
                        "name": name,
                        "rank": "A1" if len(racers) < 2 else "B1",
                        "st": ".15",
                        "tilt": "-0.5",
                        "time": "6.68",
                        "power": 80,
                        "turn_offset": 20 + ((len(racers) + 1) * 10)
                    })
                if len(racers) >= 6:
                    break
    except Exception:
        pass
        
    return racers

def build_race_struct(racers, race_num):
    while len(racers) < 6:
        idx = len(racers) + 1
        racers.append({
            "name": f"選手{idx}",
            "rank": "B1",
            "st": ".15",
            "tilt": "-0.5",
            "time": "6.70",
            "power": 70,
            "turn_offset": 20 + (idx * 10)
        })

    target_combos = [
        ("1 - 2 - 3", "本命", "tag-honmei"), ("1 - 3 - 2", "本命", "tag-honmei"),
        ("1 - 2 - 4", "本命", "tag-honmei"), ("1 - 4 - 2", "本命", "tag-honmei"),
        ("1 - 3 - 4", "本命", "tag-honmei"), ("2 - 1 - 3", "狙い", "tag-nerai"),
        ("2 - 3 - 1", "狙い", "tag-nerai"), ("3 - 1 - 2", "狙い", "tag-nerai"),
        ("3 - 2 - 1", "穴", "tag-ana"),     ("4 - 1 - 2", "穴", "tag-ana")
    ]
    bets = [{"num": num, "tag": tag, "style": style, "odds": "--"} for num, tag, style in target_combos]

    return {
        "weather": {"weather": "晴", "wind_speed": "2m", "wind_direction": "追い風", "wave": "2cm"},
        "summary_tag": "【本命濃厚】" if int(race_num) % 2 == 1 else "【捲り一閃】",
        "racers": racers,
        "comment": f"1号艇【{racers[0]['name']}】中心の組み立て。",
        "sub_comment": "インコース安定感重視。",
        "bets": bets
    }

def process_single_stadium(code, date_str):
    name = STADIUM_NAMES.get(code, "競艇場")
    races_dict = {}
    
    for r in range(1, 13):
        r_str = str(r)
        racers = fetch_race_racers(code, r_str, date_str)
        races_dict[r_str] = build_race_struct(racers, r)
        
    stadium_json = {
        "date": date_str,
        "stadium_code": code,
        "stadium_name": name,
        "races": races_dict
    }
    
    with open(f"stadium_{code}.json", "w", encoding="utf-8") as f:
        json.dump(stadium_json, f, ensure_ascii=False, indent=2)
        
    print(f" -> 出走表作成完了: stadium_{code}.json ({name})")
    return code, name

def main():
    start_time = time.time()
    today_str = datetime.now().strftime("%Y%m%d")
    print(f"[{today_str}] データ取得・生成開始...")

    active_codes = get_active_stadiums_today(today_str)
    
    if not active_codes:
        print("⚠️ 本日開催データが空のため、デフォルト場を設定します。")
        active_codes = ["04", "05", "07", "08", "09", "11", "12", "13", "14", "18", "19", "22", "23"]

    active_stadiums = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_single_stadium, code, today_str) for code in active_codes]
        for future in futures:
            try:
                code, name = future.result()
                active_stadiums.append({"code": code, "name": name})
            except Exception as e:
                print(f"処理エラー: {e}")

    active_codes.sort()
    active_stadiums.sort(key=lambda x: x["code"])

    index_data = {
        "date": today_str,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active_codes": active_codes,
        "active_stadiums": active_stadiums
    }
    
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 'data.json' 保存完了！（対象: {len(active_codes)}場 / 所要時間: {time.time() - start_time:.2f}秒）")

if __name__ == "__main__":
    main()
