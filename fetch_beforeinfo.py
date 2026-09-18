import os
import json
import time
import re
import urllib.request
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

HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch_url(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

def fetch_before_info(jcd, rno, date_str):
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={date_str}"
    html = fetch_url(url)
    res = {"weather": {"weather": "-", "wind_speed": "-", "wind_direction": "-", "wave": "-"}, "extra": {}}
    if not html: return res
    soup = BeautifulSoup(html, "html.parser")
    
    # 気象
    w_unit = soup.select_one(".weather1")
    if w_unit:
        txt = w_unit.text
        m_w = re.search(r"天候\s*([^\s]+)", txt)
        m_wind = re.search(r"風速\s*(\d+m)", txt)
        m_wave = re.search(r"波高\s*(\d+cm)", txt)
        m_dir = re.search(r"風向\s*([^\s]+)", txt)
        res["weather"] = {
            "weather": m_w.group(1) if m_w else "-",
            "wind_speed": m_wind.group(1) if m_wind else "-",
            "wind_direction": m_dir.group(1) if m_dir else "追い風",
            "wave": m_wave.group(1) if m_wave else "-"
        }
    # 艇別展示データ
    for idx in range(1, 7):
        tbody = soup.find("tbody", class_=re.compile(f"is-boatColor{idx}"))
        if not tbody: continue
        txts = [td.text.strip() for td in tbody.find_all(["td", "th"]) if td.text.strip()]
        ex_t, tilt, st = "-", "-", "-"
        for t in txts:
            if re.match(r"^6\.\d{2}$", t): ex_t = t
            elif re.match(r"^[-+]?(?:0|1|2|3)\.(?:5|0)$", t) or t == "-0.5": tilt = t
            elif re.match(r"^(?:[FL]\.)?\d{2}$", t) or re.match(r"^\.\d{2}$", t): st = t
        res["extra"][str(idx)] = {"st": st, "tilt": tilt, "time": ex_t}
    return res

def process_stadium(code, date_str, master_data, cache_key):
    st_races = master_data.get(code, {})
    races_dict = {}
    for r in range(1, 13):
        r_str = str(r)
        racers = st_races.get(r_str, [])
        info = fetch_before_info(code, r_str, date_str)
        
        combined_racers = []
        for idx, racer in enumerate(racers, start=1):
            ex = info["extra"].get(str(idx), {})
            combined_racers.append({
                "name": racer["name"],
                "rank": racer["rank"],
                "st": ex.get("st", "-"),
                "tilt": ex.get("tilt", "-"),
                "time": ex.get("time", "-")
            })
            
        races_dict[r_str] = {
            "weather": info["weather"],
            "summary_tag": "【本命濃厚】" if r % 2 == 1 else "【捲り一閃】",
            "racers": combined_racers,
            "comment": f"1号艇【{combined_racers[0]['name']}】中心の組み立て。",
            "sub_comment": "展示STとチルト変化に注意。"
        }
        
    out = {
        "date": date_str, "stadium_code": code,
        "stadium_name": STADIUM_NAMES.get(code, "競艇場"),
        "cache_buster": cache_key, "races": races_dict
    }
    with open(f"stadium_{code}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

def main():
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    today_str = now.strftime("%Y%m%d")
    cache_key = str(int(now.timestamp() * 1000))
    
    if not os.path.exists("racers_master.json"):
        print("マスターデータが存在しません。")
        return

    with open("racers_master.json", "r", encoding="utf-8") as f:
        master_data = json.load(f)

    active_codes = sorted(list(master_data.keys()))
    with ThreadPoolExecutor(max_workers=5) as ex:
        for code in active_codes:
            ex.submit(process_stadium, code, today_str, master_data, cache_key)

    index_data = {
        "date": today_str, "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "cache_buster": cache_key, "active_codes": active_codes,
        "active_stadiums": [{"code": c, "name": STADIUM_NAMES[c]} for c in active_codes]
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print("✅ 展示データリアルタイム更新完了")

if __name__ == "__main__":
    main()
