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
    """ 公式直前情報ページ解析（気象・展示タイム・チルト・展示ST） """
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={date_str}"
    html = fetch_url(url)
    
    before_data = {
        "weather": {"weather": "-", "wind_speed": "-", "wind_direction": "-", "wave": "-"},
        "racers_extra": {}
    }
    for idx in range(1, 7):
        before_data["racers_extra"][str(idx)] = {"st": "-", "tilt": "-", "time": "-"}

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

def run_ai_analysis(racers_data, weather):
    """
    【AI展開予測エンジン】
    直前展示・選手階級・気象条件からパワー評価、展開分類、コメント、買い目を自動生成
    """
    # 1. 展示タイムの最高値を計算
    valid_times = [float(r["time"]) for r in racers_data if r["time"] != "-" and re.match(r"^6\.\d{2}$", r["time"])]
    best_time = min(valid_times) if valid_times else None

    # 2. 各艇のパワー数値算出
    scores = {}
    for idx, r in enumerate(racers_data, start=1):
        b_str = str(idx)
        score = 50.0  # 基礎点
        
        # 級別補正
        rank = r.get("rank", "B1")
        if rank == "A1": score += 20
        elif rank == "A2": score += 12
        elif rank == "B1": score += 5
        
        # 枠番補正（1号艇優位）
        if idx == 1: score += 15
        elif idx == 2: score += 8
        elif idx == 3: score += 5

        # 展示タイム補正
        if best_time and r["time"] != "-":
            try:
                t_val = float(r["time"])
                diff = round(t_val - best_time, 2)
                if diff == 0.0: score += 15       # 一番時計
                elif diff <= 0.03: score += 10
                elif diff <= 0.06: score += 5
                else: score -= 5
            except ValueError: pass

        # 展示ST補正
        st = r.get("st", "-")
        if st != "-":
            m_st = re.search(r"\.(\d{2})", st)
            if m_st:
                val = int(m_st.group(1))
                if val <= 10: score += 10         # 鋭いスタート
                elif val <= 15: score += 5
                elif val >= 22: score -= 5

        # チルト補正
        tilt = r.get("tilt", "-")
        if tilt in ["0.5", "1.0", "1.5", "2.0", "3.0"]:
            score += 8  # 伸び仕様の可能性

        scores[b_str] = min(max(int(score), 35), 98) # 35〜98の範囲に収める

    # パワー値を反映
    for idx, r in enumerate(racers_data, start=1):
        r["power"] = scores[str(idx)]
        r["turn_offset"] = 15 + (idx * 12)

    # 3. 展開分類・予想コメントの自動生成
    c1_score = scores.get("1", 50)
    c2_score = scores.get("2", 50)
    c3_score = scores.get("3", 50)
    c4_score = scores.get("4", 50)
    
    top_boat = max(scores, key=scores.get)
    r1_name = racers_data[0]["name"] if racers_data[0]["name"] != "-" else "1号艇"
    
    wind_spd = weather.get("wind_speed", "0m")
    is_strong_wind = False
    try:
        if int(wind_spd.replace("m", "")) >= 5: is_strong_wind = True
    except ValueError: pass

    if c1_score >= 75 and not is_strong_wind:
        summary_tag = "【本命濃厚】"
        comment = f"1号艇【{r1_name}】が展示気配・イン信頼度ともに優勢。スタート決めて一気に逃げ切る。"
        sub_comment = "対抗軸は2・3号艇の差し・握りマイ。紐荒れ注意。"
    elif c3_score >= 70 or c4_score >= 70:
        summary_tag = "【捲り一閃】"
        comment = f"センター枠の展開が鍵。{top_boat}号艇が展示タイム良好で鋭いダッシュ戦から強襲を狙う。"
        sub_comment = "1号艇の残しと、展開突く展開差し艇の浮上に期待。"
    elif is_strong_wind:
        summary_tag = "【荒れ模様】"
        comment = f"風速{wind_spd}の水面悪化により波乱含み。ターンのズレから高配当の決着も十分。"
        sub_comment = "展示STが安定している艇の紐穴・逆転に注意。"
    else:
        summary_tag = "【混戦模様】"
        comment = f"実力伯仲の激戦カード。軸判定は慎重に、展示STを踏み込んでいる艇を評価したい。"
        sub_comment = "スタート展示の行き足とスリット直後の足色を要重視。"

    # 4. 推奨買い目（10点）の動的選出
    # スコア上位艇を組み合わせたスマート買い目生成
    sorted_boats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    b1, b2, b3, b4 = sorted_boats[0][0], sorted_boats[1][0], sorted_boats[2][0], sorted_boats[3][0]

    # 基本の組み合わせパターン
    if b1 == "1":
        combos = [
            (f"1 - {b2} - {b3}", "本命", "tag-honmei"),
            (f"1 - {b3} - {b2}", "本命", "tag-honmei"),
            (f"1 - {b2} - {b4}", "本命", "tag-honmei"),
            (f"1 - {b4} - {b2}", "本命", "tag-honmei"),
            (f"1 - {b3} - {b4}", "狙い", "tag-nerai"),
            (f"{b2} - 1 - {b3}", "狙い", "tag-nerai"),
            (f"{b2} - {b3} - 1", "狙い", "tag-nerai"),
            (f"{b3} - 1 - {b2}", "穴", "tag-ana"),
            (f"{b3} - {b2} - 1", "穴", "tag-ana"),
            (f"{b4} - 1 - {b2}", "穴", "tag-ana")
        ]
    else:
        combos = [
            (f"{b1} - 1 - {b2}", "本命", "tag-honmei"),
            (f"{b1} - {b2} - 1", "本命", "tag-honmei"),
            (f"1 - {b1} - {b2}", "本命", "tag-honmei"),
            (f"{b1} - {b2} - {b3}", "狙い", "tag-nerai"),
            (f"{b2} - {b1} - 1", "狙い", "tag-nerai"),
            (f"1 - {b2} - {b1}", "狙い", "tag-nerai"),
            (f"{b2} - 1 - {b3}", "狙い", "tag-nerai"),
            (f"{b3} - {b1} - 1", "穴", "tag-ana"),
            (f"{b3} - {b2} - 1", "穴", "tag-ana"),
            (f"1 - {b3} - {b4}", "穴", "tag-ana")
        ]

    bets = [{"num": num, "tag": tag, "style": style, "odds": "--"} for num, tag, style in combos]

    return summary_tag, comment, sub_comment, bets

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
                "power": 50,
                "turn_offset": 20
            })

        # AI展開解析エンジン実行
        summary_tag, comment, sub_comment, bets = run_ai_analysis(combined_racers, before_info["weather"])

        races_dict[r_str] = {
            "weather": before_info["weather"],
            "summary_tag": summary_tag,
            "racers": combined_racers,
            "comment": comment,
            "sub_comment": sub_comment,
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

    print(f"🤖 AI展開解析スクレイピング完了（所要時間: {time.time() - start_time:.2f}秒）")

if __name__ == "__main__":
    main()
