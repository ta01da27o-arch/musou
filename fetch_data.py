import os
import json
import time
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

STADIUM_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
})

def fetch_url(url, timeout=12):
    try:
        resp = SESSION.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None

def get_active_stadiums_today(date_str):
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    html = fetch_url(url, timeout=20)
    active_codes = []
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.select('a[href*="jcd="]'):
            m = re.search(r"jcd=(\d{2})", link.get("href", ""))
            if m and m.group(1) in STADIUM_NAMES and m.group(1) not in active_codes:
                active_codes.append(m.group(1))
    return sorted(active_codes)

def fetch_race_beforeinfo(jcd, rno, date_str):
    """ 公式直前情報ページ解析 """
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={date_str}"
    html = fetch_url(url)
    
    before_data = {
        "weather": {"weather": "-", "wind_speed": "-", "wind_direction": "-", "wave": "-"},
        "racers_extra": {}
    }
    if not html:
        return before_data

    soup = BeautifulSoup(html, "html.parser")
    
    # 1. 気象情報
    w_unit = soup.select_one(".weather1")
    if w_unit:
        txt = w_unit.text
        m_w = re.search(r"天候\s*([^\s]+)", txt)
        m_wind = re.search(r"風速\s*(\d+m)", txt)
        m_wave = re.search(r"波高\s*(\d+cm)", txt)
        m_dir = re.search(r"風向\s*([^\s]+)", txt)
        
        before_data["weather"] = {
            "weather": m_w.group(1) if m_w else "-",
            "wind_speed": m_wind.group(1) if m_wind else "-",
            "wind_direction": m_dir.group(1) if m_dir else "追い風",
            "wave": m_wave.group(1) if m_wave else "-"
        }

    # 初期化
    for idx in range(1, 7):
        before_data["racers_extra"][str(idx)] = {"st": "-", "tilt": "-", "time": "-"}

    # 2. 直前情報（展示タイム・チルト）の抽出
    for idx in range(1, 7):
        b_str = str(idx)
        tbody = soup.find("tbody", class_=re.compile(f"is-boatColor{idx}"))
        if tbody:
            tds = [td.text.strip() for td in tbody.find_all("td") if td.text.strip()]
            ex_t, tilt = "-", "-"
            for t in tds:
                if re.match(r"^6\.\d{2}$", t):
                    ex_t = t
                elif re.match(r"^[-+]?(?:0|1|2|3)\.(?:5|0)$", t) or t == "-0.5":
                    tilt = t
            before_data["racers_extra"][b_str]["time"] = ex_t
            before_data["racers_extra"][b_str]["tilt"] = tilt

    # 3. スタート展示（展示ST）の抽出
    st_table = soup.select_one("div.table1")
    if st_table:
        for row in st_table.find_all("tr"):
            row_txt = row.text.strip()
            m = re.search(r"(\d)\s+([FL]?\.\d{2})", row_txt)
            if m:
                b_num, st_val = m.group(1), m.group(2)
                if b_num in before_data["racers_extra"]:
                    before_data["racers_extra"][b_num]["st"] = st_val

    return before_data

def fetch_race_racers(jcd, rno, date_str):
    """ 公式出走表から選手名・階級を確実に抽出 """
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd}&hd={date_str}"
    html = fetch_url(url)
    racers = []
    
    if html:
        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.find_all("a", href=re.compile(r"toban=\d+"))
        for a in anchors:
            name = a.text.strip().replace("\u3000", "").replace(" ", "")
            # 該当選手が含まれる親要素（tbody/tr）から階級を取得
            parent = a.find_parent("tbody")
            rank = "B1"
            if parent:
                r_m = re.search(r"([AB][12])", parent.text)
                if r_m:
                    rank = r_m.group(1)

            if name and not any(r["name"] == name for r in racers):
                racers.append({"name": name, "rank": rank})
            if len(racers) >= 6:
                break

    while len(racers) < 6:
        racers.append({"name": "-", "rank": "-"})

    return racers

def process_single_stadium(code, date_str, cache_key):
    name = STADIUM_NAMES.get(code, "競艇場")
    races_dict = {}
    
    for r in range(1, 13):
        r_str = str(r)
        racers = fetch_race_racers(code, r_str, date_str)
        before_info = fetch_race_beforeinfo(code, r_str, date_str)
        
        combined_racers = []
        for idx, racer in enumerate(racers, start=1):
            extra = before_info["racers_extra"].get(str(idx), {})
            combined_racers.append({
                "name": racer["name"],
                "rank": racer["rank"],
                "st": extra.get("st", "-"),
                "tilt": extra.get("tilt", "-"),
                "time": extra.get("time", "-"),
                "power": 85 if idx <= 2 else 70,
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

        races_dict[r_str] = {
            "weather": before_info["weather"],
            "summary_tag": "【本命濃厚】" if r % 2 == 1 else "【捲り一閃】",
            "racers": combined_racers,
            "comment": f"1号艇【{combined_racers[0]['name']}】中心の組み立て。",
            "sub_comment": "展示STとチルト変化に注意。",
            "bets": bets
        }
        
    stadium_json = {
        "date": date_str,
        "stadium_code": code,
        "stadium_name": name,
        "cache_buster": cache_key,
        "races": races_dict
    }
    
    with open(f"stadium_{code}.json", "w", encoding="utf-8") as f:
        json.dump(stadium_json, f, ensure_ascii=False, indent=2)
        
    return code, name

def main():
    start_time = time.time()
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    today_str = now_jst.strftime("%Y%m%d")
    cache_key = str(int(now_jst.timestamp() * 1000))
    
    active_codes = get_active_stadiums_today(today_str)
    if not active_codes:
        active_codes = ["04", "05", "07", "08", "09", "11", "12", "13", "14", "18", "19", "22", "23"]

    active_stadiums = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_single_stadium, code, today_str, cache_key) for code in active_codes]
        for future in futures:
            try:
                code, name = future.result()
                active_stadiums.append({"code": code, "name": name})
            except Exception:
                pass

    active_codes.sort()
    active_stadiums.sort(key=lambda x: x["code"])

    index_data = {
        "date": today_str,
        "updated_at": now_jst.strftime("%Y-%m-%d %H:%M:%S"),
        "cache_buster": cache_key,
        "active_codes": active_codes,
        "active_stadiums": active_stadiums
    }
    
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"✅ スクレイピング完了（所要時間: {time.time() - start_time:.2f}秒）")

if __name__ == "__main__":
    main()
