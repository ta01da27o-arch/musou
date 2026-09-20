import os
import re
import json
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
    """本日開催中の競艇場一覧を取得"""
    url = "https://www.boatrace.jp/owpc/pc/race/index"
    active_stadiums = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 開催場リンクを取得
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

def get_race_close_times(jcd):
    """対象場の1R〜12Rの締切予定時刻を一括取得"""
    close_times = {}
    url = f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={jcd}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        
        # レース一覧テーブルから締切時刻を取得
        rows = soup.select("table tbody tr")
        for row in rows:
            r_text = row.text
            r_match = re.search(r"(\d{1,2})R", r_text)
            t_match = re.search(r"(\d{1,2}:\d{2})", r_text)
            if r_match and t_match:
                r_num = r_match.group(1)
                close_times[r_num] = t_match.group(1)
    except Exception as e:
        print(f"締切時刻取得エラー ({jcd}): {e}")
    return close_times

def fetch_beforeinfo(jcd, race_num):
    """直前情報（展示タイム、チルト、展示ST、進入コース、気象データ）を取得"""
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_num}&jcd={jcd}"
    data = {
        "weather": {"weather": "-", "wind_speed": "-", "wind_direction": "-", "wave": "-"},
        "racers_before": {},
        "start_display": []
    }
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        # 気象情報抽出
        weather_ele = soup.select_one(".weather1")
        if weather_ele:
            text = weather_ele.text.replace("\n", " ")
            w_match = re.search(r"天候\s*([^\s]+)", text)
            ws_match = re.search(r"風速\s*(\d+m)", text)
            wd_match = re.search(r"風向\s*([^\s]+)", text)
            wv_match = re.search(r"波高\s*(\d+cm)", text)
            
            if w_match: data["weather"]["weather"] = w_match.group(1)
            if ws_match: data["weather"]["wind_speed"] = ws_match.group(1)
            if wd_match: data["weather"]["wind_direction"] = wd_match.group(1)
            if wv_match: data["weather"]["wave"] = wv_match.group(1)

        # 直前展示データ抽出（チルト・展示タイム）
        tbl_racers = soup.select("table.tblHeader")
        if len(tbl_racers) >= 2:
            rows = tbl_racers[1].select("tbody tr")
            b_idx = 1
            for r in rows:
                tds = r.select("td")
                if len(tds) >= 4:
                    tilt = tds[2].text.strip()
                    t_time = tds[3].text.strip()
                    data["racers_before"][str(b_idx)] = {
                        "tilt": tilt if tilt else "-",
                        "time": t_time if t_time else "-"
                    }
                    b_idx += 1

        # スタート展示・進入コース順抽出
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
                        data["start_display"].append({
                            "boat": int(b_num),
                            "st": st_val
                        })
    except Exception as e:
        print(f"直前情報取得エラー ({jcd} {race_num}R): {e}")
    return data

def fetch_racelist(jcd, race_num):
    """出走表データ（選手名、級別、F/L、全国勝率など）を取得"""
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_num}&jcd={jcd}"
    racers = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        rows = soup.select("table tbody.is-fs12 tr")
        current_boat = 1
        for row in rows:
            name_ele = row.select_one(".is-fs18")
            if name_ele:
                name = name_ele.text.strip().replace(" ", "")
                rank_ele = row.select_one(".is-fs11")
                rank = rank_ele.text.strip() if rank_ele else "B1"
                
                # ST平均等の抽出
                tds = row.select("td")
                st_avg = "-"
                if len(tds) >= 6:
                    st_text = tds[5].text
                    match = re.search(r"F\d|L\d|\.\d{2}", st_text)
                    if match:
                        st_avg = match.group(0)

                racers.append({
                    "boat": current_boat,
                    "name": name,
                    "rank": rank,
                    "st": st_avg,
                    "tilt": "-",
                    "time": "-"
                })
                current_boat += 1
    except Exception as e:
        print(f"出走表取得エラー ({jcd} {race_num}R): {e}")
        # フォールバック用ダミー生成
        for i in range(1, 7):
            racers.append({"boat": i, "name": f"選手{i}", "rank": "B1", "st": ".15", "tilt": "0.0", "time": "6.80"})
    return racers

def generate_ai_prediction(racers, start_display, weather):
    """AI展開予測・スコアリングエンジン（見解・本紙タグ・裏予想・3連単10点買い目）"""
    scores = {}
    for r in racers:
        b = r["boat"]
        base_score = 10 - b  # 枠番有利（1号艇優位）
        if "A1" in r["rank"]: base_score += 4
        elif "A2" in r["rank"]: base_score += 2
        scores[b] = base_score

    # 展示ST補正
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

    # スコア順にソート
    sorted_boats = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    top1 = sorted_boats[0]
    top2 = sorted_boats[1]
    top3 = sorted_boats[2]
    top4 = sorted_boats[3]

    # AI見解生成
    if top1 == 1:
        summary_tag = "【イン絶対】"
        comment = f"1号艇が絶好の枠位置を活かしてイン速攻を決める。対抗は攻め立てる{top2}号艇。"
        sub_comment = f"{top3}号艇の展開突いたまくり差しで高配当を狙う。"
    else:
        summary_tag = "【波乱含み】"
        comment = f"{top1}号艇の気配が優勢。センター枠からの鋭い仕掛けで1号艇の逃げを脅かす。"
        sub_comment = f"1号艇が逃げ残る目も押さえつつ、{top2}号艇の連入を考慮。"

    # 3連単10点買い目生成
    bets = [
        {"num": f"{top1}-{top2}-{top3}", "tag": "本命", "style": "tag-honmei"},
        {"num": f"{top1}-{top2}-{top4}", "tag": "本命", "style": "tag-honmei"},
        {"num": f"{top1}-{top3}-{top2}", "tag": "対抗", "style": "tag-nerai"},
        {"num": f"{top1}-{top3}-{top4}", "tag": "対抗", "style": "tag-nerai"},
        {"num": f"{top1}-{top4}-{top2}", "tag": "抑え", "style": "tag-nerai"},
        {"num": f"{top2}-{top1}-{top3}", "tag": "狙い", "style": "tag-nerai"},
        {"num": f"{top2}-{top1}-{top4}", "tag": "狙い", "style": "tag-nerai"},
        {"num": f"{top2}-{top3}-{top1}", "tag": "穴", "style": "tag-ana"},
        {"num": f"{top3}-{top1}-{top2}", "tag": "大穴", "style": "tag-ana"},
        {"num": f"{top3}-{top2}-{top1}", "tag": "特穴", "style": "tag-ana"},
    ]

    return summary_tag, comment, sub_comment, bets

def process_stadium(jcd):
    """1つの競艇場の全12レースを並列・一括処理してJSON出力"""
    stadium_name = STADIUMS[jcd]
    print(f"[{stadium_name}] データ取得開始...")
    
    close_times = get_race_close_times(jcd)
    races_data = {}

    for r in range(1, 13):
        r_str = str(r)
        racers = fetch_racelist(jcd, r)
        before_data = fetch_beforeinfo(jcd, r)

        # 直前情報（チルト・展示タイム）を出走表とマージ
        for racer in racers:
            b_str = str(racer["boat"])
            if b_str in before_data["racers_before"]:
                racer["tilt"] = before_data["racers_before"][b_str]["tilt"]
                racer["time"] = before_data["racers_before"][b_str]["time"]

        # AI解析ロジック実行
        summary_tag, comment, sub_comment, bets = generate_ai_prediction(
            racers, before_data["start_display"], before_data["weather"]
        )

        races_data[r_str] = {
            "race_num": r,
            "close_time": close_times.get(r_str, "--:--"),
            "weather": before_data["weather"],
            "start_display": before_data["start_display"],
            "racers": racers,
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

    # JSONファイル保存
    file_path = f"stadium_{jcd}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print(f"[{stadium_name}] データ出力完了 -> {file_path}")

def main():
    active_stadiums = get_active_stadiums()
    if not active_stadiums:
        print("本日開催中の競艇場が見つかりませんでした。（フォールバック: 全場対象）")
        active_stadiums = list(STADIUMS.keys())

    print(f"処理対象競艇場: {active_stadiums}")
    
    # 並列実行で全場高速取得
    with ThreadPoolExecutor(max_workers=6) as executor:
        executor.map(process_stadium, active_stadiums)

if __name__ == "__main__":
    main()
