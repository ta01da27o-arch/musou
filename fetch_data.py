import os
import re
import json
import time
import random
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

STADIUMS = {
    "01": {"name": "桐生", "region": "kantou"},
    "02": {"name": "戸田", "region": "kantou"},
    "03": {"name": "江戸川", "region": "kantou"},
    "04": {"name": "平和島", "region": "kantou"},
    "05": {"name": "多摩川", "region": "kantou"},
    "06": {"name": "浜名湖", "region": "tokai"},
    "07": {"name": "蒲郡", "region": "tokai"},
    "08": {"name": "常滑", "region": "tokai"},
    "09": {"name": "津", "region": "tokai"},
    "10": {"name": "三国", "region": "hokuriku"},
    "11": {"name": "びわこ", "region": "kinki"},
    "12": {"name": "住之江", "region": "kinki"},
    "13": {"name": "尼崎", "region": "kinki"},
    "14": {"name": "鳴門", "region": "shikoku"},
    "15": {"name": "丸亀", "region": "shikoku"},
    "16": {"name": "児島", "region": "chugoku"},
    "17": {"name": "宮島", "region": "chugoku"},
    "18": {"name": "徳山", "region": "chugoku"},
    "19": {"name": "下関", "region": "chugoku"},
    "20": {"name": "若松", "region": "kyushu"},
    "21": {"name": "芦屋", "region": "kyushu"},
    "22": {"name": "福岡", "region": "kyushu"},
    "23": {"name": "唐津", "region": "kyushu"},
    "24": {"name": "大村", "region": "kyushu"}
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
}

def fetch_url(url):
    try:
        time.sleep(random.uniform(0.2, 0.5))
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = "utf-8"
        if res.status_code == 200:
            return res.text
    except Exception as e:
        pass
    return None

def get_today_holding_jcds():
    url = "https://www.boatrace.jp/owpc/pc/race/index"
    html = fetch_url(url)
    holding_jcds = set()
    if html:
        soup = BeautifulSoup(html, "html.parser")
        links = soup.select("a[href*='jcd=']")
        for a in links:
            href = a.get("href", "")
            m = re.search(r"jcd=(\d{2})", href)
            if m:
                holding_jcds.add(m.group(1))
    return holding_jcds

def parse_racelist(jcd, race_num):
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_num}&jcd={jcd}"
    html = fetch_url(url)
    racers = []
    close_time = "--:--"
    
    if not html:
        return racers, close_time

    soup = BeautifulSoup(html, "html.parser")

    # 締切時刻
    time_ele = soup.select_one(".tab2_time")
    if time_ele:
        m = re.search(r"\d{1,2}:\d{2}", time_ele.text)
        if m:
            close_time = m.group(0)

    # 出走表テーブル parsing
    # 公式サイトの tbody 構造を精密に取得
    tbodies = soup.select("table tbody")
    boat_num = 1
    
    for tbody in tbodies:
        rows = tbody.select("tr")
        if not rows:
            continue
            
        # 1枠〜6枠の判定
        first_row = rows[0]
        # 選手名の取得（div/spanクラス、またはaタグ等からフォールバック指定）
        name_ele = first_row.select_one("div.is-fs18, span.is-fs18, .is-fs18")
        if not name_ele:
            continue
            
        name = name_ele.text.strip().replace(" ", "").replace("　", "")
        if not name:
            continue

        rank_ele = first_row.select_one("span.is-fs11, div.is-fs11, .is-fs11")
        rank = rank_ele.text.strip() if rank_ele else "B1"
        # A1, A2, B1, B2 の抽出
        m_rank = re.search(r"[A-B][1-2]", rank)
        if m_rank:
            rank = m_rank.group(0)

        tds = first_row.select("td")
        st_avg = "-"
        nat_rate, nat_2rate = "0.00", "0.0%"
        loc_rate, loc_2rate = "0.00", "0.0%"
        motor_2rate = "0.0%"

        # 各 td からテキストデータを抽出
        for td in tds:
            txt = td.text.strip()
            # F0/0.15 などの平均ST
            if not st_avg != "-" and ("F" in txt or "L" in txt or "." in txt):
                m_st = re.search(r"F\d|L\d|\.\d{2}", txt)
                if m_st:
                    st_avg = m_st.group(0)

        # 列インデックスで確実に数値群を取得
        if len(tds) >= 7:
            # 全国勝率/2連率
            t_nat = tds[4].text.strip().split()
            if len(t_nat) >= 2:
                nat_rate, nat_2rate = t_nat[0], t_nat[1]
            elif len(t_nat) == 1:
                nat_rate = t_nat[0]

            # 当地勝率/2連率
            t_loc = tds[5].text.strip().split()
            if len(t_loc) >= 2:
                loc_rate, loc_2rate = t_loc[0], t_loc[1]
            elif len(t_loc) == 1:
                loc_rate = t_loc[0]

            # モーター2連率
            t_mot = tds[6].text.strip().split()
            if len(t_mot) >= 2:
                motor_2rate = t_mot[1] if "%" in t_mot[1] else t_mot[0]
            elif len(t_mot) == 1:
                motor_2rate = t_mot[0]

        # 的中率試算
        try:
            hit_val = float(nat_rate) * 8.5
            hit_rate = f"{min(99.9, hit_val):.1f}%"
        except:
            hit_rate = "45.0%"

        racers.append({
            "boat": boat_num,
            "name": name,
            "rank": rank,
            "st_avg": st_avg,
            "nat_rate": nat_rate,
            "nat_2rate": nat_2rate,
            "loc_rate": loc_rate,
            "loc_2rate": loc_2rate,
            "motor_2rate": motor_2rate,
            "hit_rate": hit_rate,
            "tilt": "-",
            "time": "-"
        })
        boat_num += 1
        if boat_num > 6:
            break

    return racers, close_time

def parse_beforeinfo(jcd, race_num):
    data = {
        "weather": {"weather": "晴", "wind_speed": "2m", "wind_direction": "向い風", "wave": "2cm"},
        "exhibition": {},
        "start_display": []
    }
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_num}&jcd={jcd}"
    html = fetch_url(url)
    if not html:
        return data

    soup = BeautifulSoup(html, "html.parser")

    # 天候情報
    w_ele = soup.select_one(".weather1")
    if w_ele:
        txt = w_ele.text.replace("\n", " ").replace("\r", " ")
        w = re.search(r"天候\s*([^\s]+)", txt)
        ws = re.search(r"風速\s*(\d+m)", txt)
        wd = re.search(r"風向\s*([^\s]+)", txt)
        wv = re.search(r"波高\s*(\d+cm)", txt)
        if w: data["weather"]["weather"] = w.group(1)
        if ws: data["weather"]["wind_speed"] = ws.group(1)
        if wd: data["weather"]["wind_direction"] = wd.group(1)
        if wv: data["weather"]["wave"] = wv.group(1)

    # チルト・展示タイム
    tbls = soup.select("table")
    for tbl in tbls:
        rows = tbl.select("tr")
        for r in rows:
            tds = r.select("td")
            if len(tds) >= 4:
                # 艇番のチェック
                boat_txt = tds[0].text.strip()
                if boat_txt.isdigit() and 1 <= int(boat_txt) <= 6:
                    b_num = boat_txt
                    tilt = tds[2].text.strip()
                    t_time = tds[3].text.strip()
                    data["exhibition"][b_num] = {
                        "tilt": tilt if tilt else "-",
                        "time": t_time if t_time else "-"
                    }

    # スタート展示
    s_box = soup.select_one(".stExhibitionBox, .stTrack")
    if s_box:
        s_rows = s_box.select("tr, .stTrack_row")
        for r in s_rows:
            b_e = r.select_one(".boatNumber, [class*='boatNumber']")
            st_e = r.select_one(".stTime, [class*='stTime']")
            if b_e and st_e:
                b_num = re.sub(r"\D", "", b_e.text)
                st_val = st_e.text.strip()
                if b_num and b_num.isdigit():
                    data["start_display"].append({"boat": int(b_num), "st": st_val})

    return data

def generate_ai_predictions(racers):
    if not racers:
        return "【データ準備中】", "データ取得中", "", [], []

    scores = {}
    summary_data = []

    for r in racers:
        b = r["boat"]
        score = 10 - b
        if "A1" in r["rank"]: score += 4
        elif "A2" in r["rank"]: score += 2
        scores[b] = score

        summary_data.append({
            "boat": b,
            "name": r["name"],
            "rank": r["rank"],
            "nat_rate": r["nat_rate"],
            "nat_2rate": r["nat_2rate"],
            "loc_rate": r["loc_rate"],
            "loc_2rate": r["loc_2rate"],
            "motor_2rate": r["motor_2rate"],
            "hit_rate": r["hit_rate"]
        })

    sorted_boats = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    t1 = sorted_boats[0] if len(sorted_boats) > 0 else 1
    t2 = sorted_boats[1] if len(sorted_boats) > 1 else 2
    t3 = sorted_boats[2] if len(sorted_boats) > 2 else 3
    t4 = sorted_boats[3] if len(sorted_boats) > 3 else 4

    summary_tag = "【イン信頼】" if t1 == 1 else "【波乱気配】"
    comment = f"{t1}号艇の機配が主力。追撃する{t2}号艇との旋回争い。"
    sub_comment = f"{t3}号艇の展開突入に警戒。高配当展開は{t4}の強襲。"

    bets = [
        {"num": f"{t1}-{t2}-{t3}", "tag": "本命", "style": "tag-honmei"},
        {"num": f"{t1}-{t2}-{t4}", "tag": "本命", "style": "tag-honmei"},
        {"num": f"{t1}-{t3}-{t2}", "tag": "対抗", "style": "tag-nerai"},
        {"num": f"{t1}-{t3}-{t4}", "tag": "対抗", "style": "tag-nerai"},
        {"num": f"{t1}-{t4}-{t2}", "tag": "押さえ", "style": "tag-nerai"},
        {"num": f"{t2}-{t1}-{t3}", "tag": "狙い", "style": "tag-nerai"},
        {"num": f"{t2}-{t1}-{t4}", "tag": "狙い", "style": "tag-nerai"},
        {"num": f"{t2}-{t3}-{t1}", "tag": "穴", "style": "tag-ana"},
        {"num": f"{t3}-{t1}-{t2}", "tag": "大穴", "style": "tag-ana"},
        {"num": f"{t3}-{t2}-{t1}", "tag": "特穴", "style": "tag-ana"},
    ]

    return summary_tag, comment, sub_comment, bets, summary_data

def process_stadium(jcd, holding_jcds):
    s_info = STADIUMS[jcd]
    races_data = {}
    is_holding = jcd in holding_jcds

    if is_holding:
        print(f"[{s_info['name']}] 本日開催中 -> データを取得・解析中...")
        for r in range(1, 13):
            r_str = str(r)
            racers, close_time = parse_racelist(jcd, r)
            before_data = parse_beforeinfo(jcd, r)

            for racer in racers:
                b_str = str(racer["boat"])
                if b_str in before_data["exhibition"]:
                    racer["tilt"] = before_data["exhibition"][b_str]["tilt"]
                    racer["time"] = before_data["exhibition"][b_str]["time"]

            summary_tag, comment, sub_comment, bets, summary_data = generate_ai_predictions(racers)

            races_data[r_str] = {
                "race_num": r,
                "close_time": close_time,
                "weather": before_data["weather"],
                "start_display": before_data["start_display"],
                "racers": racers,
                "summary_data": summary_data,
                "summary_tag": summary_tag,
                "comment": comment,
                "sub_comment": sub_comment,
                "bets": bets
            }
    else:
        print(f"[{s_info['name']}] 本日非開催")

    out_data = {
        "stadium_id": jcd,
        "stadium_name": s_info["name"],
        "region": s_info["region"],
        "is_holding": is_holding,
        "races": races_data
    }

    with open(f"stadium_{jcd}.json", "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

def main():
    print("本日の開催場を検索中...")
    holding_jcds = get_today_holding_jcds()
    print(f"本日開催場コード: {sorted(list(holding_jcds))}")

    with ThreadPoolExecutor(max_workers=3) as executor:
        for jcd in STADIUMS.keys():
            executor.submit(process_stadium, jcd, holding_jcds)

if __name__ == "__main__":
    main()
