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
    "蒲郡": "07", "常滑": "08", "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16", "宮島": "17", "徳山": "18",
    "下関": "19", "若松": "20", "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24"
}

def clean_text(text):
    if not text:
        return "-"
    cleaned = re.sub(r'\s+', ' ', text).strip()
    return cleaned if cleaned else "-"

def fetch_url_with_retry(url, headers, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=headers, timeout=timeout)
            if res.status_code == 200:
                return res
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.5)
                continue
    return None

def get_active_stadiums(today_str, headers):
    index_url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={today_str}"
    active_codes = []
    
    res = fetch_url_with_retry(index_url, headers)
    if res:
        soup = BeautifulSoup(res.content, "html.parser")
        links = soup.find_all("a", href=re.compile(r'jcd=\d{2}'))
        for a in links:
            match = re.search(r'jcd=(\d{2})', a['href'])
            if match:
                code = match.group(1)
                if code not in active_codes:
                    active_codes.append(code)
                
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
            # 1. 出走表（基本情報）の取得
            racelist_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_no}&jcd={code}&hd={today_str}"
            res_list = fetch_url_with_retry(racelist_url, headers)
            if not res_list:
                continue

            soup_list = BeautifulSoup(res_list.content, "html.parser")
            tbodies = soup_list.find_all("tbody", class_="is-fs12")

            if not tbodies:
                continue

            racers = []
            for tbody in tbodies:
                name_el = tbody.find("div", class_="is-fs18")
                name = clean_text(name_el.get_text()) if name_el else "不明"
                
                rank = "-"
                rank_match = re.search(r'\b(A1|A2|B1|B2)\b', tbody.get_text())
                if rank_match:
                    rank = rank_match.group(1)

                racers.append({
                    "name": name,
                    "rank": rank,
                    "st": "-",
                    "tilt": "-",
                    "time": "-"
                })

            # 2. 直前情報（展示タイム・チルト・気象データ）の取得
            before_url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_no}&jcd={code}&hd={today_str}"
            res_before = fetch_url_with_retry(before_url, headers)
            
            weather_data = {"weather": "-", "wind_speed": "-", "wind_direction": "-", "wave": "-"}

            if res_before:
                soup_before = BeautifulSoup(res_before.content, "html.parser")
                
                # 気象情報の抽出
                weather_box = soup_before.find("div", class_="weather1")
                if weather_box:
                    # 天気
                    w_el = weather_box.find("span", class_="weather1_bodyUnitLabelData")
                    if w_el:
                        weather_data["weather"] = clean_text(w_el.get_text())
                    
                    # 風速・波高の解析
                    box_text = weather_box.get_text()
                    wind_m = re.search(r'風速\s*(\d+m)', box_text)
                    if wind_m:
                        weather_data["wind_speed"] = wind_m.group(1)
                        
                    wave_m = re.search(r'波高\s*(\d+cm)', box_text)
                    if wave_m:
                        weather_data["wave"] = wave_m.group(1)
                        
                    # 風向き（クラス名からの判定）
                    wind_dir_el = weather_box.find("p", class_=re.compile(r'is-wind\d+'))
                    if wind_dir_el:
                        weather_data["wind_direction"] = clean_text(wind_dir_el.get_text())

                # 展示数値（展示ST, チルト, 展示タイム）の抽出
                ex_tbodies = soup_before.find_all("tbody", class_="is-fs12")
                for idx, tbody in enumerate(ex_tbodies):
                    if idx < len(racers):
                        tds = tbody.find_all("td")
                        for td in tds:
                            text = clean_text(td.get_text())
                            # チルト (-0.5, 0.0, 0.5 等)
                            if re.match(r'^[-+]?\d\.\d$', text) and racers[idx]["tilt"] == "-":
                                racers[idx]["tilt"] = text
                            # 展示タイム (6.x～7.x)
                            elif re.match(r'^6\.\d{2}$|^7\.\d{2}$', text) and racers[idx]["time"] == "-":
                                racers[idx]["time"] = text
                            # 展示ST (.15 等)
                            elif re.match(r'^\.\d{2}$', text) and racers[idx]["st"] == "-":
                                racers[idx]["st"] = text

            if racers:
                all_data["stadiums"][stadium_name][str(race_no)] = {
                    "racers": racers,
                    "weather": weather_data
                }
                total_races_fetched += 1
            
            time.sleep(0.1)

    if total_races_fetched == 0 and os.path.exists("data.json"):
        print("新規データが取得できなかったため、既存の data.json を保持します。")
    else:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        print(f"data.json を本日（{today_str}）の全データ（気象・展示含む）で更新完了！（取得レース数: {total_races_fetched}）")

    elapsed_time = round(time.time() - start_time, 1)
    print(f"処理完了！（所要時間: {elapsed_time}秒）")

if __name__ == "__main__":
    fetch_all_race_data()
