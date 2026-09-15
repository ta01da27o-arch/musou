import requests
from bs4 import BeautifulSoup
import json
import datetime
import zoneinfo
import time
import re
import os

STADIUM_CODES = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04", "多摩川": "05", "浜名湖": "06",
    "蒲郡": "07", "常滑": "08", "津": "09", "三国": "10", "びわco": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16", "宮島": "17", "徳山": "18",
    "下関": "19", "若松": "20", "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24"
}

def clean_text(text):
    if not text:
        return "-"
    cleaned = re.sub(r'\s+', ' ', text).strip()
    return cleaned if cleaned else "-"

def get_active_stadiums(today_str, headers, retries=3):
    index_url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={today_str}"
    active_codes = []
    
    for attempt in range(retries):
        try:
            res = requests.get(index_url, headers=headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.content, "html.parser")
                links = soup.find_all("a", href=re.compile(r'jcd=\d{2}'))
                for a in links:
                    match = re.search(r'jcd=(\d{2})', a['href'])
                    if match:
                        code = match.group(1)
                        if code not in active_codes:
                            active_codes.append(code)
                if active_codes:
                    break
        except Exception as e:
            print(f"開催場一覧取得試行 {attempt + 1}/{retries} 失敗: {e}")
            if attempt < retries - 1:
                time.sleep(2)
                
    return active_codes

def fetch_all_race_data():
    start_time = time.time()
    
    jst_tz = zoneinfo.ZoneInfo("Asia/Tokyo")
    now_jst = datetime.datetime.now(jst_tz)
    today_str = now_jst.strftime("%Y%m%d")
    
    all_data = {
        "updated_at": now_jst.strftime("%Y-%m-%d %H:%M:%S"),
        "date": today_str,
        "stadiums": {}
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"[{today_str} (JST)] 本日の開催場を検索中...")
    active_codes = get_active_stadiums(today_str, headers)
    
    code_to_name = {v: k for k, v in STADIUM_CODES.items()}
    active_names = [code_to_name[c] for c in active_codes if c in code_to_name]
    
    print(f"本日開催中の会場 ({len(active_names)}場): {', '.join(active_names)}")

    total_races_fetched = 0

    for stadium_name, code in STADIUM_CODES.items():
        all_data["stadiums"][stadium_name] = {}
        
        if code not in active_codes:
            continue

        for race_no in range(1, 13):
            url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_no}&jcd={code}&hd={today_str}"
            
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code != 200:
                    continue

                soup = BeautifulSoup(res.content, "html.parser")
                tbodies = soup.find_all("tbody", class_="is-fs12")

                if not tbodies:
                    continue

                racers = []
                for tbody in tbodies:
                    # 1. 選手名
                    name_el = tbody.find("div", class_="is-fs18")
                    name = clean_text(name_el.get_text()) if name_el else "不明"
                    
                    # 2. 級別 (A1, A2, B1, B2 を確実取得)
                    rank = "-"
                    rank_match = re.search(r'\b(A1|A2|B1|B2)\b', tbody.get_text())
                    if rank_match:
                        rank = rank_match.group(1)

                    # 3. 直前展示数値等の抽出
                    tds = tbody.find_all("td")
                    st, tilt, time_val = "-", "-", "-"

                    for td in tds:
                        text = clean_text(td.get_text())
                        if re.match(r'^[-+]?\d\.\d$', text) and tilt == "-":
                            tilt = text
                        elif re.match(r'^6\.\d{2}$|^7\.\d{2}$', text) and time_val == "-":
                            time_val = text
                        elif re.match(r'^\.\d{2}$', text) and st == "-":
                            st = text

                    racers.append({
                        "name": name,
                        "rank": rank,
                        "st": st,
                        "tilt": tilt,
                        "time": time_val
                    })

                if racers:
                    all_data["stadiums"][stadium_name][str(race_no)] = {
                        "racers": racers
                    }
                    total_races_fetched += 1

            except Exception as e:
                print(f"エラースキップ ({stadium_name} {race_no}R): {e}")
                continue
            
            time.sleep(0.1)

    if total_races_fetched == 0 and os.path.exists("data.json"):
        print("新規データが取得できなかったため、既存の data.json を保持します。")
    else:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        print(f"data.json を本日（{today_str}）のデータで更新完了！（取得レース数: {total_races_fetched}）")

    elapsed_time = round(time.time() - start_time, 1)
    print(f"処理完了！（所要時間: {elapsed_time}秒）")

if __name__ == "__main__":
    fetch_all_race_data()
