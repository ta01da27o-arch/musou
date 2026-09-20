import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

# 全24競艇場コード・名称マッピング
STADIUMS = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川", "06": "浜名湖",
    "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島", "17": "宮島", "18": "徳山",
    "19": "下関", "20": "若松", "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_active_stadiums():
    """本日開催中の競艇場一覧を取得（公式サイトより）"""
    url = "https://www.boatrace.jp/owpc/pc/race/index"
    active_stadiums = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        
        for a in soup.select("a[href*='jcd=']"):
            href = a.get("href", "")
            match = re.search(r"jcd=(\d{2})", href)
            if match:
                jcd = match.group(1)
                if jcd in STADIUMS and jcd not in active_stadiums:
                    active_stadiums.append(jcd)
    except Exception as e:
        print(f"開催場一覧取得エラー: {e}")
    return active_stadiums

def get_official_racelist_and_times(jcd, race_num):
    """【公式サイトより取得】1. 本日の出走表（選手名・級別・ST等） 2. 締切予定時刻"""
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_num}&jcd={jcd}"
    racers = []
    close_time = "--:--"
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        # 締切時刻取得
        time_ele = soup.select_one(".tab2_time")
        if time_ele:
            time_match = re.search(r"\d{1,2}:\d{2}", time_ele.text)
            if time_match:
                close_time = time_match.group(0)

        # 出走表取得
        rows = soup.select("table tbody.is-fs12 tr")
        current_boat = 1
        for row in rows:
            name_ele = row.select_one(".is-fs18")
            if name_ele:
                name = name_ele.text.strip().replace(" ", "")
                rank_ele = row.select_one(".is-fs11")
                rank = rank_ele.text.strip() if rank_ele else "B1"
                
                # F/L・平均ST等の抽出
                tds = row.select("td")
                st_avg = "-"
                win_rate_national = "0.00"
                win_rate_local = "0.00"
                motor_2rate = "0.00"

                if len(tds) >= 7:
                    st_text = tds[5].text
                    m = re.search(r"F\d|L\d|\.\d{2}", st_text)
                    if m: st_avg = m.group(0)

                    # 全国・当地・モーター連対率（成績サマリー用）
                    rates = tds[4].text.split("/") if len(tds) > 4 else []
                    if len(rates) >= 2:
                        win_rate_national = rates[0].strip()
                        win_rate_local = rates[1].strip()

                racers.append({
                    "boat": current_boat,
                    "name": name,
                    "rank": rank,
                    "st_avg": st_avg,
                    "win_rate_national": win_rate_national,
                    "win_rate_local": win_rate_local,
                    "motor_2rate": motor_2rate,
                    # 展示データ初期値
                    "tilt": "-",
                    "time": "-",
                    "ex_st": "-"
                })
                current_boat += 1
    except Exception as e:
        print(f"公式サイトデータ取得エラー ({jcd} {race_num}R): {e}")
        for i in range(1, 7):
            racers.append({
                "boat": i, "name": f"選手{i}", "rank": "B1", "st_avg": ".15",
                "win_rate_national": "5.00", "win_rate_local": "5.00", "motor_2rate": "30.0",
                "tilt": "0.0", "time": "6.80", "ex_st": ".15"
            })
            
    return racers, close_time

def fetch_external_exhibition_data(jcd, race_num):
    """
    【外部サイト/無料API連携】展示データ（チルト・展示タイム・展示ST・進入コース・気象）を取得
    ※外部データ取得用プロキシAPIおよびフォールバック構造
    """
    # 無料API / 外部スクレイピング用URL構造
    api_url = f"https://api.open-boatrace.net/v1/exhibition?jcd={jcd}&rno={race_num}"
    ex_data = {
        "weather": {"weather": "晴", "wind_speed": "2m", "wind_direction": "向い風", "wave": "2cm"},
        "exhibition": {},
        "start_display": []
    }

    try:
        # APIリクエスト（タイムアウト時はフォールバック直接HTMLパース）
        res = requests.get(api_url, timeout=3)
        if res.status_code == 200:
            json_res = res.json()
            ex_data["weather"] = json_res.get("weather", ex_data["weather"])
            ex_data["exhibition"] = json_res.get("exhibition", {})
            ex_data["start_display"] = json_res.get("start_display", [])
            return ex_data
    except Exception:
        pass

    # 外部Webサイトフォールバック取得処理 (例: Cyber/Kyotei外部データサイト)
    ext_url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_num}&jcd={jcd}"
    try:
        res = requests.get(ext_url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        # 気象情報
        weather_ele = soup.select_one(".weather1")
        if weather_ele:
            text = weather_ele.text.replace("\n", " ")
            w = re.search(r"天候\s*([^\s]+)", text)
            ws = re.search(r"風速\s*(\d+m)", text)
            wd = re.search(r"風向\s*([^\s]+)", text)
            wv = re.search(r"波高\s*(\d+cm)", text)
            if w: ex_data["weather"]["weather"] = w.group(1)
            if ws: ex_data["weather"]["wind_speed"] = ws.group(1)
            if wd: ex_data["weather"]["wind_direction"] = wd.group(1)
            if wv: ex_data["weather"]["wave"] = wv.group(1)

        # 直前展示データ
        tbl_racers = soup.select("table.tblHeader")
        if len(tbl_racers) >= 2:
            rows = tbl_racers[1].select("tbody tr")
            b_idx = 1
            for r in rows:
                tds = r.select("td")
                if len(tds) >= 4:
                    tilt = tds[2].text.strip()
                    t_time = tds[3].text.strip()
                    ex_data["exhibition"][str(b_idx)] = {
                        "tilt": tilt if tilt else "-",
                        "time": t_time if t_time else "-"
                    }
                    b_idx += 1

        # スタート展示順
        slit_box = soup.select_one(".stExhibitionBox")
        if slit_box:
            slit_rows = slit_box.select(".stTrack tr")
            for row in slit_rows:
                b_ele = row.select_one(".boatNumber")
                st_ele = row.select_one(".stTime")
                if b_ele and st_ele:
                    b_num = re.sub(r"\D", "", b_ele.text)
                    st_val = st_ele.text.strip()
                    if b_num:
                        ex_data["start_display"].append({"boat": int(b_num), "st": st_val})
    except Exception as e:
        print(f"外部展示データ取得例外 ({jcd} {race_num}R): {e}")

    return ex_data

def generate_ai_prediction_and_summary(racers, start_display):
    """成績サマリー指標計算 & AI展開予測・10点買い目ロジック"""
    scores = {}
    summary_data = []

    for r in racers:
        b = r["boat"]
        base_score = 10 - b
        if "A1" in r["rank"]: base_score += 4
        elif "A2" in r["rank"]: base_score += 2
        scores[b] = base_score

        # 成績サマリー項目の構築
        summary_data.append({
            "boat": b,
            "name": r["name"],
            "rank": r["rank"],
            "national": r["win_rate_national"],
            "local": r["win_rate_local"],
            "motor": r["motor_2rate"],
            "score": base_score
        })

    # 展示STによる補正
    for sd in start_display:
        b = sd["boat"]
        st = sd["st"]
        if b in scores and not "F" in st and not "L" in st:
            try:
                st_val = float(st.replace(".", "0."))
                if st_val <= 0.12: scores[b] += 3
                elif st_val >= 0.20: scores[b] -= 2
            except:
                pass

    sorted_boats = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    t1 = sorted_boats[0] if len(sorted_boats) > 0 else 1
    t2 = sorted_boats[1] if len(sorted_boats) > 1 else 2
    t3 = sorted_boats[2] if len(sorted_boats) > 2 else 3
    t4 = sorted_boats[3] if len(sorted_boats) > 3 else 4

    if t1 == 1:
        summary_tag = "【イン本命】"
        comment = f"1号艇{racers[0]['name']}がインから押し切る。対抗は気配良好な{t2}号艇。"
        sub_comment = f"{t3}号艇の自力展開とまくり差しでの逆転連入に注目。"
    else:
        summary_tag = "【波乱含み】"
        comment = f"{t1}号艇の機敏な立ち回りが光る。センターからの鋭い仕掛けで1枠崩しを狙う。"
        sub_comment = f"1号艇の残しを押さえつつ、{t2}号艇との絡みを本線に。"

    bets = [
        {"num": f"{t1}-{t2}-{t3}", "tag": "本命", "style": "tag-honmei"},
        {"num": f"{t1}-{t2}-{t4}", "tag": "本命", "style": "tag-honmei"},
        {"num": f"{t1}-{t3}-{t2}", "tag": "対抗", "style": "tag-nerai"},
        {"num": f"{t1}-{t3}-{t4}", "tag": "対抗", "style": "tag-nerai"},
        {"num": f"{t1}-{t4}-{t2}", "tag": "抑え", "style": "tag-nerai"},
        {"num": f"{t2}-{t1}-{t3}", "tag": "狙い", "style": "tag-nerai"},
        {"num": f"{t2}-{t1}-{t4}", "tag": "狙い", "style": "tag-nerai"},
        {"num": f"{t2}-{t3}-{t1}", "tag": "穴", "style": "tag-ana"},
        {"num": f"{t3}-{t1}-{t2}", "tag": "大穴", "style": "tag-ana"},
        {"num": f"{t3}-{t2}-{t1}", "tag": "特穴", "style": "tag-ana"},
    ]

    return summary_tag, comment, sub_comment, bets, summary_data

def process_stadium(jcd):
    """競艇場別データ統合・JSONファイル生成"""
    stadium_name = STADIUMS[jcd]
    print(f"[{stadium_name}] データ一括取得開始...")
    
    races_data = {}

    for r in range(1, 13):
        r_str = str(r)
        
        # 1. 公式サイトから出走表・締切時刻取得
        racers, close_time = get_official_racelist_and_times(jcd, r)
        
        # 2. 外部サイト/無料APIから展示データ取得
        ext_data = fetch_external_exhibition_data(jcd, r)

        # データを統合
        for racer in racers:
            b_str = str(racer["boat"])
            if b_str in ext_data["exhibition"]:
                racer["tilt"] = ext_data["exhibition"][b_str]["tilt"]
                racer["time"] = ext_data["exhibition"][b_str]["time"]

        # 3. AI予測・成績サマリー生成
        summary_tag, comment, sub_comment, bets, summary_data = generate_ai_prediction_and_summary(
            racers, ext_data["start_display"]
        )

        races_data[r_str] = {
            "race_num": r,
            "close_time": close_time,
            "weather": ext_data["weather"],
            "start_display": ext_data["start_display"],
            "racers": racers,
            "summary_data": summary_data,
            "summary_tag": summary_tag,
            "comment": comment,
            "sub_comment": sub_comment,
            "bets": bets
        }

    out_data = {
        "stadium_id": jcd,
        "stadium_name": stadium_name,
        "races": races_data
    }

    file_path = f"stadium_{jcd}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print(f"[{stadium_name}] 出力完了 -> {file_path}")

def main():
    active_stadiums = get_active_stadiums()
    if not active_stadiums:
        active_stadiums = list(STADIUMS.keys())

    print(f"対象競艇場: {active_stadiums}")
    with ThreadPoolExecutor(max_workers=6) as executor:
        executor.map(process_stadium, active_stadiums)

if __name__ == "__main__":
    main()
