import requests
from bs4 import BeautifulSoup
import json
import datetime
import time

STADIUM_CODES = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04", "多摩川": "05", "浜名湖": "06",
    "蒲郡": "07", "常滑": "08", "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16", "宮島": "17", "徳山": "18",
    "下関": "19", "若松": "20", "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24"
}

def fetch_page_with_retry(url, headers, retries=2):
    """ タイムアウト対策：失敗しても指定回数リトライする関数 """
    for attempt in range(retries):
        try:
            # タイムアウトを15秒に延長
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response
        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                time.sleep(1) # 1秒待って再試行
                continue
            else:
                raise e
    return None

def fetch_all_race_data():
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    all_data = {
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": today_str,
        "stadiums": {}
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"[{today_str}] 全国の出走表データ取得を開始します...")

    for stadium_name, code in STADIUM_CODES.items():
        all_data["stadiums"][stadium_name] = {}
        
        for race_no in range(1, 13):
            url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_no}&jcd={code}&hd={today_str}"
            
            try:
                res = fetch_page_with_retry(url, headers)
                if not res:
                    continue

                soup = BeautifulSoup(res.content, "html.parser")
                tbodies = soup.find_all("tbody", class_="is-fs12")

                if not tbodies:
                    continue  # 開催がない場合はスキップ

                racers = []
                for tbody in tbodies:
                    name_el = tbody.find("div", class_="is-fs18")
                    name = name_el.get_text(strip=True) if name_el else "不明"
                    
                    rank_el = tbody.find("span", class_="is-fs11")
                    rank = rank_el.get_text(strip=True) if rank_el else "-"

                    tds = tbody.find_all("td")
                    st = tds[4].get_text(strip=True) if len(tds) > 4 else "-"
                    tilt = tds[5].get_text(strip=True) if len(tds) > 5 else "-"
                    time_val = tds[6].get_text(strip=True) if len(tds) > 6 else "-"

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
                    print(f"成功: {stadium_name} {race_no}R ({len(racers)}名)")

            except Exception as e:
                print(f"エラースキップ ({stadium_name} {race_no}R): {e}")
                continue
            
            # サーバー負荷軽減とブロック防止のため0.3秒待機
            time.sleep(0.3)

    # data.json に保存
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print("data.json の正常生成が完了しました！")

if __name__ == "__main__":
    fetch_all_race_data()
