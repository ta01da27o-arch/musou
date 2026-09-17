import os
import json
import time
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup

STADIUM_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

# ブラウザ偽装用ヘッダー
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Referer": "https://www.boatrace.jp/"
}

def fetch_html(url):
    """ セッションを維持してアクセス制限を回避するリクエスト処理 """
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        res = session.get(url, timeout=10)
        res.encoding = 'utf-8' if 'charset=utf-8' in res.headers.get('content-type', '').lower() else 'euc-jp'
        if res.status_code == 200 and "Cloudflare" not in res.text and "Access Denied" not in res.text:
            return res.text
    except Exception as e:
        print(f"Fetch error ({url}): {e}")
    return None

def get_active_stadiums(date_str):
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    html = fetch_html(url)
    active_codes = []
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            match = re.search(r"jcd=(\d{2})", a["href"])
            if match:
                code = match.group(1)
                if code not in active_codes:
                    active_codes.append(code)
    return sorted(active_codes)

def fetch_race_data(code, race_num, date_str):
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_num}&jcd={code}&hd={date_str}"
    html = fetch_html(url)
    
    racers = []
    if html:
        soup = BeautifulSoup(html, "html.parser")
        
        # 選手名の抽出パターン
        # 1. リンクタグ href="...toban=..."
        for a in soup.find_all("a", href=re.compile(r"toban")):
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

    # データ不備時の補充
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
        "summary_tag": "【本命濃厚】" if race_num % 2 == 1 else "【捲り一閃】",
        "racers": racers,
        "comment": f"1号艇【{racers[0]['name']}】中心の組み立て。",
        "sub_comment": "インコース安定感重視。",
        "bets": bets
    }

def process_single_stadium(code, date_str):
    races_data = {str(r): fetch_race_data(code, r, date_str) for r in range(1, 13)}
    stadium_json = {
        "date": date_str,
        "stadium_code": code,
        "stadium_name": STADIUM_NAMES.get(code, "競艇場"),
        "races": races_data
    }
    with open(f"stadium_{code}.json", "w", encoding="utf-8") as f:
        json.dump(stadium_json, f, ensure_ascii=False, indent=2)
    return code, STADIUM_NAMES.get(code, "")

def main():
    today_str = datetime.now().strftime("%Y%m%d")
    active_codes = get_active_stadiums(today_str)
    if not active_codes:
        active_codes = ["04", "05", "07", "08", "09", "11", "12", "13", "14", "18", "19", "22", "23"]

    active_stadiums = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_single_stadium, code, today_str) for code in active_codes]
        for future in futures:
            code, name = future.result()
            active_stadiums.append({"code": code, "name": name})

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

if __name__ == "__main__":
    main()
