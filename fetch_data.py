import os
import json
import time
import re
import urllib.request
import tempfile
from datetime import datetime

# LZH解凍用ライブラリ
try:
    import lhafile
except ImportError:
    lhafile = None

STADIUM_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

def download_and_extract_lzh(date_str):
    """
    公式のB{YYMMDD}.lzh (または.TXT)をダウンロードし、LZH解凍してテキストを抽出する
    """
    yy = date_str[-6:-4]
    mm = date_str[-4:-2]
    dd = date_str[-2:]
    
    # 配信ファイル名のパターン
    filename_txt = f"B{yy}{mm}{dd}.TXT"
    filename_lzh = f"b{yy}{mm}{dd}.lzh"
    
    urls = [
        f"https://www.boatrace.jp/owpc/pc/extra/data/download/{filename_lzh}",
        f"https://www.boatrace.jp/owpc/pc/extra/data/download/{filename_txt}"
    ]
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for url in urls:
        print(f"ダウンロード試行: {url}")
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                data_bytes = response.read()

                # 1. lhafile ライブラリによるLZH解凍
                if lhafile:
                    try:
                        with tempfile.NamedTemporaryFile(delete=False) as tmp:
                            tmp.write(data_bytes)
                            tmp_path = tmp.name

                        lf = lhafile.Lhafile(tmp_path)
                        for info in lf.infolist():
                            extracted_bytes = lf.read(info.filename)
                            try:
                                txt = extracted_bytes.decode('cp932')
                            except UnicodeDecodeError:
                                txt = extracted_bytes.decode('euc-jp', errors='ignore')
                            
                            os.remove(tmp_path)
                            print(f"✅ LZH解凍成功: {info.filename}")
                            return txt
                        os.remove(tmp_path)
                    except Exception as e:
                        print(f"lhafile 解凍エラー: {e}")

                # 2. 直接テキストの場合のフォールバック
                try:
                    txt = data_bytes.decode('cp932')
                    if "BB3#" in txt or "ボートレース" in txt or "番組表" in txt:
                        print("✅ 生テキスト取得完了")
                        return txt
                except Exception:
                    pass

        except Exception as e:
            print(f"取得失敗 ({url}): {e}")

    return None

def parse_program_txt(txt_content):
    """ 番組表テキストから全開催場・全レース・全選手データを抽出 """
    stadium_data = {}
    current_jcd = None
    current_rno = None

    lines = txt_content.splitlines()

    for line in lines:
        # 場コード判定 (BB3#04 等)
        if "BB3#" in line:
            m = re.search(r"BB3#(\d{2})", line)
            if m:
                current_jcd = m.group(1)
                if current_jcd in STADIUM_NAMES and current_jcd not in stadium_data:
                    stadium_data[current_jcd] = {}
                continue

        # 場名ダイレクト検出（バックアップ）
        for code, name in STADIUM_NAMES.items():
            if f"ボートレース{name}" in line or f"［{name}］" in line or f"【{name}】" in line or (name in line and "第" in line and "日" in line):
                current_jcd = code
                if current_jcd not in stadium_data:
                    stadium_data[current_jcd] = {}
                break

        # レース番号判定 (1R 〜 12R)
        r_match = re.search(r"(\d{1,2})\s*Ｒ", line) or re.search(r"(\d{1,2})R", line)
        if r_match and current_jcd:
            r_num = int(r_match.group(1))
            if 1 <= r_num <= 12:
                current_rno = str(r_num)
                if current_rno not in stadium_data[current_jcd]:
                    stadium_data[current_jcd][current_rno] = []

        # 選手情報行の抽出（艇番 1-6 + 登録番号 4桁）
        if current_jcd and current_rno:
            p_match = re.search(r"([1-6])\s+(\d{4})\s+([^\s]+)\s+([AB][12])", line)
            if p_match:
                lane = int(p_match.group(1))
                toban = p_match.group(2)
                raw_name = p_match.group(3).replace("　", " ").strip()
                rank = p_match.group(4)

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
    print(f"[{today_str}] 公式データ解析開始...")

    txt = download_and_extract_lzh(today_str)
    
    active_codes = []
    active_stadiums = []

    if txt:
        parsed_data = parse_program_txt(txt)
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
                
            print(f" -> 出走表作成完了: stadium_{code}.json")

    # データが抽出できなかった場合の予備動作
    if not active_codes:
        print("⚠️ 抽出結果が0件のため、基本開催リストを生成します。")
        default_codes = ["04", "05", "07", "08", "09", "11", "12", "13", "14", "18", "19", "22", "23"]
        for code in default_codes:
            name = STADIUM_NAMES.get(code, "競艇場")
            active_codes.append(code)
            active_stadiums.append({"code": code, "name": name})
            
            races_dict = {str(r): build_race_struct([], r) for r in range(1, 13)}
            stadium_json = {
                "date": today_str,
                "stadium_code": code,
                "stadium_name": name,
                "races": races_dict
            }
            with open(f"stadium_{code}.json", "w", encoding="utf-8") as f:
                json.dump(stadium_json, f, ensure_ascii=False, indent=2)

    active_codes.sort()
    active_stadiums.sort(key=lambda x: x["code"])

    index_data = {
        "date": today_str,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active_codes": active_codes,
        "active_stadiums": active_stadiums
    }
    
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 全データ作成完了！（所要時間: {time.time() - start_time:.2f}秒）")

if __name__ == "__main__":
    main()
