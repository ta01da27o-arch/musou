import os
import json
import time
import re
import urllib.request
import lzma
from datetime import datetime

STADIUM_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

def download_official_program_txt(date_str):
    """
    公式のダウンロード用テキスト番組表を取得する
    URL形式: https://www.boatrace.jp/owpc/pc/extra/data/download/B{YYMMDD}.TXT
    """
    yy = date_str[2:4]
    mm = date_str[4:6]
    dd = date_str[6:8]
    filename = f"B{yy}{mm}{dd}.TXT"
    url = f"https://www.boatrace.jp/owpc/pc/extra/data/download/{filename}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            # Shift_JIS(CP932) または EUC-JP でデコード
            content = response.read()
            try:
                return content.decode('cp932')
            except UnicodeDecodeError:
                return content.decode('euc-jp', errors='ignore')
    except Exception as e:
        print(f"番組表テキストの取得に失敗しました: {e}")
        return None

def parse_program_txt(txt_content, date_str):
    """
    番組表テキストを解析して各競艇場・各レースの出走選手データを抽出
    """
    stadium_data = {}
    
    # 競艇場ごとに分割（「◆競艇場名」で区切られているパターンに対応）
    # 例: BB3#04... 等のヘッダー解析
    lines = txt_content.splitlines()
    
    current_jcd = None
    current_rno = None
    
    for line in lines:
        # 場コード判定（行内に場名やコードが含まれるヘッダーを識別）
        for code, name in STADIUM_NAMES.items():
            if f"ボートレース{name}" in line or f"［{name}］" in line or f"【{name}】" in line:
                current_jcd = code
                if current_jcd not in stadium_data:
                    stadium_data[current_jcd] = {}
                break

        # レース番号判定
        r_match = re.search(r"(\d{1,2})\s*Ｒ", line)
        if r_match and current_jcd:
            current_rno = str(int(r_match.group(1)))
            if current_rno not in stadium_data[current_jcd]:
                stadium_data[current_jcd][current_rno] = []

        # 選手情報行の抽出（登録番号 4桁数字 + 選手名 + 級別）
        # 例: 1 4321 毒島　　誠 A1 ...
        if current_jcd and current_rno:
            boat_match = re.search(r"^\s*([1-6])\s+(\d{4})\s+([^\s]+)\s+([AB][12])", line)
            if boat_match:
                lane = int(boat_match.group(1))
                toban = boat_match.group(2)
                raw_name = boat_match.group(3).replace("　", " ")
                rank = boat_match.group(4)
                
                # 同一艇の二重追加防止
                racers = stadium_data[current_jcd][current_rno]
                if len(racers) < 6:
                    racers.append({
                        "name": raw_name,
                        "rank": rank,
                        "st": ".15",
                        "tilt": "-0.5",
                        "time": "6.68",
                        "power": 85 if rank in ["A1", "A2"] else 70,
                        "turn_offset": 20 + (lane * 10)
                    })

    return stadium_data

def build_race_struct(racers, race_num):
    # 6艇揃っていない場合の補填
    while len(racers) < 6:
        idx = len(racers) + 1
        racers.append({
            "name": f"選手{idx}",
            "rank": "B1",
            "st": ".15",
            "tilt": "-0.5",
            "time": "6.70",
            "power": 70,
            "turn_offset": 20 + (idx * 10)
        })

    target_combos = [
        ("1 - 2 - 3", "本命", "tag-honmei"), ("1 - 3 - 2", "本命", "tag-honmei"),
        ("1 - 2 - 4", "本命", "tag-honmei"), ("1 - 4 - 2", "本命", "tag-honmei"),
        ("1 - 3 - 4", "本命", "tag-honmei"), ("2 - 1 - 3", "狙い", "tag-nerai"),
        ("2 - 3 - 1", "狙い", "tag-nerai"), ("3 - 1 - 2", "狙い", "tag-nerai"),
        ("3 - 2 - 1", "穴", "tag-ana"),     ("4 - 1 - 2", "穴", "tag-ana")
    ]
    bets = [{"num": num, "tag": tag, "style": style, "odds": "--"} for num, tag, style in target_combos]

    return {
        "weather": {"weather": "晴", "wind_speed": "2m", "wind_direction": "追い風", "wave": "2cm"},
        "summary_tag": "【本命濃厚】" if int(race_num) % 2 == 1 else "【捲り一閃】",
        "racers": racers,
        "comment": f"1号艇【{racers[0]['name']}】中心の組み立て。",
        "sub_comment": "インコース安定感重視。",
        "bets": bets
    }

def main():
    start_time = time.time()
    today_str = datetime.now().strftime("%Y%m%d")
    print(f"[{today_str}] 公式テキストデータ取得中...")

    txt = download_official_program_txt(today_str)
    
    active_codes = []
    active_stadiums = []

    if txt:
        parsed_data = parse_program_txt(txt, today_str)
        active_codes = sorted(list(parsed_data.keys()))
        
        for code in active_codes:
            name = STADIUM_NAMES.get(code, "競艇場")
            active_stadiums.append({"code": code, "name": name})
            
            races_dict = {}
            for r in range(1, 13):
                r_str = str(r)
                racers = parsed_data[code].get(r_str, [])
                races_dict[r_str] = build_race_struct(racers, r)
                
            stadium_json = {
                "date": today_str,
                "stadium_code": code,
                "stadium_name": name,
                "races": races_dict
            }
            
            with open(f"stadium_{code}.json", "w", encoding="utf-8") as f:
                json.dump(stadium_json, f, ensure_ascii=False, indent=2)
                
            print(f" -> 保存完了: stadium_{code}.json")
    else:
        print("番組表テキストのダウンロードに失敗したため、デフォルトデータで生成します。")

    # index用 data.json の出力
    index_data = {
        "date": today_str,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active_codes": active_codes,
        "active_stadiums": active_stadiums
    }
    
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 全データ生成完了！（所要時間: {time.time() - start_time:.2f}秒）")

if __name__ == "__main__":
    main()
