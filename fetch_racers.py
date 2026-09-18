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

def main():
    jst = timezone(timedelta(hours=9))
    today_str = datetime.now(jst).strftime("%Y%m%d")
    
    # 開催場取得
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={today_str}"
    html = fetch_url(url)
    active_codes = []
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.select('a[href*="jcd="]'):
            m = re.search(r"jcd=(\d{2})", link.get("href", ""))
            if m and m.group(1) in STADIUM_NAMES and m.group(1) not in active_codes:
                active_codes.append(m.group(1))
    
    master_data = {}
    for code in active_codes:
        stadium_races = {}
        for r in range(1, 13):
            r_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={r}&jcd={code}&hd={today_str}"
            r_html = fetch_url(r_url)
            racers = []
            if r_html:
                soup = BeautifulSoup(r_html, "html.parser")
                for a in soup.find_all("a", href=re.compile(r"toban=\d+")):
                    name = a.text.strip().replace("\u3000", " ")
                    if name and not any(x["name"] == name for x in racers):
                        racers.append({"name": name, "rank": "A1" if len(racers) < 2 else "B1"})
                    if len(racers) >= 6: break
            while len(racers) < 6:
                racers.append({"name": f"選手{len(racers)+1}", "rank": "B1"})
            stadium_races[str(r)] = racers
        master_data[code] = stadium_races

    with open("racers_master.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=2)
    print("✅ 朝の出走表マスターデータ作成完了")

if __name__ == "__main__":
    main()
