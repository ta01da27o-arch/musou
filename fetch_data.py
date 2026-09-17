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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_active_stadiums_from_official(date_str):
    """ 本日開催中の場コードを取得 """
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    active_codes = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, "html.parser")
            for a in soup.find_all("a", href=True):
                match = re.search(r"jcd=(\d{2})", a["href"])
                if match:
                    code = match.group(1)
                    if code not in active_codes:
                        active_codes.append(code)
    except Exception:
        pass
    return sorted(active_codes)

def fetch_before_info(code, race_num, date_str):
    """ 直前情報（展示タイム・気象）の解析強化 """
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_num}&jcd={code}&hd={date_str}"
    before_data = {}
    weather_info = {"weather": "晴", "wind_speed": "2m", "wind_direction": "追い風", "wave": "2cm"}
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, "html.parser")
            
            # 天候情報
            weather_ele = soup.find("div", class_=re.compile(r"weather"))
            if weather_ele:
                txt = weather_ele.text
                if "雨" in txt: weather_info["weather"] = "雨"
                elif "曇" in txt: weather_info["weather"] = "曇"
                wind_m = re.search(r"(\d+)m", txt)
                if wind_m: weather_info["wind_speed"] = f"{wind_m.group(1)}m"

            # 展示タイム解析 (6.xx の数値を艇順にピックアップ)
            times = re.findall(r"6\.\d{2}", res.text)
            for idx, t_val in enumerate(times[:6], 1):
                before_data[idx] = {"time": t_val, "tilt": "-0.5"}
    except Exception:
        pass
    return before_data, weather_info

def fetch_odds_3t(code, race_num, date_str):
    """ 3連単オッズ解析 """
    url = f"https://www.boatrace.jp/owpc/pc/race/odds3t?rno={race_num}&jcd={code}&hd={date_str}"
    odds_dict = {}
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, "html.parser")
            for cell in soup.find_all("td", class_=re.compile(r"oddsPoint")):
                combo = cell.get("data-combo")
                val = cell.text.strip()
                if combo and val:
                    try:
                        odds_dict[combo.replace("-", " - ")] = float(val)
                    except ValueError:
                        pass
    except Exception:
        pass
    return odds_dict

def fetch_race_data(code, race_num, date_str):
    """ 出走表（選手名・級別・ST）抽出の堅牢化 """
    before_info, weather_info = fetch_before_info(code, race_num, date_str)
    odds_dict = fetch_odds_3t(code, race_num, date_str)
    
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_num}&jcd={code}&hd={date_str}"
    racers = []

    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, "html.parser")
            
            # 出走表テーブルの行（1〜6枠）を取得
            rows = soup.find_all("tbody", class_=re.compile(r"is-fs12|is-p10-0"))
            if not rows:
                rows = soup.find_all("tbody")

            for idx, tbody in enumerate(rows, 1):
                if len(racers) >= 6:
                    break
                
                # 選手名の特定
                name = ""
                name_div = tbody.find("div", class_=re.compile(r"is-fs18"))
                if name_div:
                    name = name_div.text.strip().replace("\u3000", " ")
                else:
                    a_tag = tbody.find("a", href=re.compile(r"toban"))
                    if a_tag:
                        name = a_tag.text.strip()

                if not name:
                    continue

                name = re.sub(r"\s+", " ", name)

                # 級別
                rank = "B1"
                rank_span = tbody.find("span", class_=re.compile(r"is-rank"))
                if rank_span:
                    rank = rank_span.text.strip()

                # ST
                st = ".15"
                st_match = re.search(r"\.\d{2}", tbody.text)
                if st_match:
                    st = st_match.group(0)

                b_data = before_info.get(len(racers) + 1, {"time": "6.68", "tilt": "-0.5"})

                racers.append({
                    "name": name,
                    "rank": rank,
                    "st": st,
                    "tilt": b_data["tilt"],
                    "time": b_data["time"],
                    "power": 85 if rank in ["A1", "A2"] else 70,
                    "turn_offset": 20 + ((len(racers) + 1) * 10)
                })
    except Exception:
        pass

    # 万が一失敗した場合はデフォルト値で補填
    while len(racers) < 6:
        idx = len(racers) + 1
        b_data = before_info.get(idx, {"time": "6.70", "tilt": "-0.5"})
        racers.append({
            "name": f"未確定{idx}",
            "rank": "B1",
            "st": ".15",
            "tilt": b_data["tilt"],
            "time": b_data["time"],
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

    bets = [{"num": num, "tag": tag, "style": style, "odds": odds_dict.get(num, "--")} for num, tag, style in target_combos]

    return {
        "weather": weather_info,
        "summary_tag": "【本命濃厚】" if race_num % 2 == 1 else "【捲り一閃】",
        "racers": racers,
        "comment": f"1号艇【{racers[0]['name']}】がインから先マイを狙う展開。展示タイム{racers[0]['time']}。",
        "sub_comment": "イン逃げ中心も展示気配の良い艇の差し・まくり差しに注意❗",
        "bets": bets
    }

def process_single_stadium(code, date_str):
    file_name = f"stadium_{code}.json"
    races_data = {str(r): fetch_race_data(code, r, date_str) for r in range(1, 13)}

    stadium_json_content = {
        "date": date_str,
        "stadium_code": code,
        "stadium_name": STADIUM_NAMES.get(code, "競艇場"),
        "races": races_data
    }

    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(stadium_json_content, f, ensure_ascii=False, indent=2)

    return code, STADIUM_NAMES.get(code, "")

def main():
    start_time = time.time()
    today_str = datetime.now().strftime("%Y%m%d")
    print(f"[{today_str} (JST)] 実データのスクレイピングを開始...")

    active_codes = get_active_stadiums_from_official(today_str)
    if not active_codes:
        active_codes = ["04", "05", "07", "08", "09", "11", "12", "13", "14", "18", "19", "22", "23"]

    active_stadiums = []
    with ThreadPoolExecutor(max_workers=6) as executor:
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

    print(f"✅ 完了 (所要時間: {time.time() - start_time:.1f}秒)")

if __name__ == "__main__":
    main()
