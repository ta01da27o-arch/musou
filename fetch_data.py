import os
import re
import json
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

# 全24競艇場（ID・名称・地区グループ定義）
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
}

def check_holding_and_get_racelist(jcd, race_num):
    """公式サイトから出走表を取得し、本日開催中か判定する"""
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_num}&jcd={jcd}"
    racers = []
    close_time = "--:--"
    is_holding = False
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        # 出走表テーブル行が存在すれば本日開催と判定
        rows = soup.select("table tbody.is-fs12 tr")
        if rows:
            is_holding = True
            time_ele = soup.select_one(".tab2_time")
            if time_ele:
                m = re.search(r"\d{1,2}:\d{2}", time_ele.text)
                if m: close_time = m.group(0)

            current_boat = 1
            for row in rows:
                name_ele = row.select_one(".is-fs18")
                if name_ele:
                    name = name_ele.text.strip().replace(" ", "").replace("　", "")
                    rank_ele = row.select_one(".is-fs11")
                    rank = rank_ele.text.strip() if rank_ele else "B1"
                    
                    tds = row.select("td")
                    nat_rate, nat_2rate = "0.00", "0.0%"
                    loc_rate, loc_2rate = "0.00", "0.0%"
                    motor_2rate = "0.0%"
                    st_avg = "-"

                    if len(tds) >= 7:
                        nat_text = tds[4].text.strip().split()
                        if len(nat_text) >= 2: nat_rate, nat_2rate = nat_text[0], nat_text[1]
                        
                        loc_text = tds[5].text.strip().split() if len(tds) > 5 else []
                        if len(loc_text) >= 2: loc_rate, loc_2rate = loc_text[0], loc_text[1]

                        m_text = tds[6].text.strip().split() if len(tds) > 6 else []
                        if len(m_text) >= 2: motor_2rate = m_text[1]

                        st_text = tds[3].text
                        m_st = re.search(r"F\d|L\d|\.\d{2}", st_text)
                        if m_st: st_avg = m_st.group(0)

                    # 的中率指標の計算
                    try:
                        hit_rate = f"{min(99.9, float(nat_rate) * 8.5):.1f}%"
                    except:
                        hit_rate = "45.0%"

                    racers.append({
                        "boat": current_boat,
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
                    current_boat += 1
    except Exception as e:
        print(f"取得エラー ({jcd} {race_num}R): {e}")

    return is_holding, racers, close_time

def fetch_beforeinfo_data(jcd, race_num):
    """直前情報（天候・展示タイム・チルト・スリット展示）の取得"""
    data = {
        "weather": {"weather": "晴", "wind_speed": "2m", "wind_direction": "向い風", "wave": "2cm"},
        "exhibition": {},
        "start_display": []
    }
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_num}&jcd={jcd}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        # 気象情報
        w_ele = soup.select_one(".weather1")
        if w_ele:
            txt = w_ele.text.replace("\n", " ")
            w = re.search(r"天候\s*([^\s]+)", txt)
            ws = re.search(r"風速\s*(\d+m)", txt)
            wd = re.search(r"風向\s*([^\s]+)", txt)
            wv = re.search(r"波高\s*(\d+cm)", txt)
            if w: data["weather"]["weather"] = w.group(1)
            if ws: data["weather"]["wind_speed"] = ws.group(1)
            if wd: data["weather"]["wind_direction"] = wd.group(1)
            if wv: data["weather"]["wave"] = wv.group(1)

        # 展示タイム・チルト
        tbls = soup.select("table.tblHeader")
        if len(tbls) >= 2:
            rows = tbls[1].select("tbody tr")
            b_idx = 1
            for r in rows:
                tds = r.select("td")
                if len(tds) >= 4:
                    tilt = tds[2].text.strip()
                    t_time = tds[3].text.strip()
                    data["exhibition"][str(b_idx)] = {
                        "tilt": tilt if tilt else "-",
                        "time": t_time if t_time else "-"
                    }
                    b_idx += 1

        # スリット展示
        s_box = soup.select_one(".stExhibitionBox")
        if s_box:
            s_rows = s_box.select(".stTrack tr")
            for r in s_rows:
                b_e = r.select_one(".boatNumber")
                st_e = r.select_one(".stTime")
                if b_e and st_e:
                    b_num = re.sub(r"\D", "", b_e.text)
                    st_val = st_e.text.strip()
                    if b_num:
                        data["start_display"].append({"boat": int(b_num), "st": st_val})
    except Exception as e:
        print(f"直前情報取得エラー: {e}")

    return data

def generate_ai_predictions(racers):
    """AI展開予想と10点買い目の生成"""
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

def process_stadium(jcd):
    s_info = STADIUMS[jcd]
    races_data = {}
    
    # 1Rの開催チェック
    is_holding, racers_1r, close_time_1r = check_holding_and_get_racelist(jcd, 1)

    if is_holding:
        print(f"[{s_info['name']}] 本日開催中 - データ解析を開始します")
        for r in range(1, 13):
            r_str = str(r)
            if r == 1:
                racers, close_time = racers_1r, close_time_1r
            else:
                _, racers, close_time = check_holding_and_get_racelist(jcd, r)

            before_data = fetch_beforeinfo_data(jcd, r)

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
    with ThreadPoolExecutor(max_workers=6) as executor:
        executor.map(process_stadium, STADIUMS.keys())

if __name__ == "__main__":
    main()
