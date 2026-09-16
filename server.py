from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import random

app = FastAPI()

# フロントエンドからのクロスドメイン通信(CORS)を許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 選手名プール
RACERS = ["毒島 誠", "峰 竜太", "茅原 悠紀", "馬場 貴也", "池田 浩二", "菊地 孝平", "白井 英治", "瓜生 正義", "石野 貴之"]
RANKS = ["A1", "A1", "A1", "A2", "A1", "B1"]
WINDS = ["北", "南", "東", "西", "北東", "南西"]

@app.get("/api/race/{stadium_code}/{race_num}")
def get_race_data(stadium_code: str, race_num: str):
    """
    指定された競艇場・レース番号の直前展示＆出走データを返すAPI
    ※実際運用時は BOATRACE 公式サイト等のスクレイピングロジックをここに統合します
    """
    selected_racers = random.sample(RACERS, 6)
    
    racers_data = []
    for i in range(6):
        racers_data.append({
            "name": selected_racers[i],
            "rank": RANKS[i],
            "st": f".{random.randint(8, 18):02d}",
            "tilt": "-0.5" if random.random() > 0.2 else "0.0",
            "time": f"6.{random.randint(60, 78):02d}",
            "power": random.randint(65, 95)
        })

    # レース展開の生成（整合性のとれたストーリー）
    top1 = racers_data[0]['name']
    top2 = racers_data[1]['name']
    top3 = racers_data[2]['name']
    top4 = racers_data[3]['name']
    
    comment = f"<strong>1号艇・{top1}</strong>が絶好のスタートから1マークを先マイして独走態勢へ。<strong>3号艇・{top3}</strong>が果敢にまくりを狙うもインの抵抗にあって外へ流れ、その隙を逃さず内へ鋭く差し込んだ<strong>2号艇・{top2}</strong>と<strong>4号艇・{top4}</strong>が2着争いを展開する。"

    return {
        "stadium_code": stadium_code,
        "race_num": race_num,
        "weather": {
            "weather": random.choice(["晴", "曇", "雨"]),
            "wind_speed": f"{random.randint(1, 6)}m",
            "wind_direction": f"{random.choice(WINDS)}風",
            "wave": f"{random.randint(1, 5)}cm"
        },
        "racers": racers_data,
        "comment": comment,
        "bets": [
            {"num": "1 - 2 - 4", "tag": "本命", "style": "tag-honmei"},
            {"num": "1 - 4 - 2", "tag": "本命", "style": "tag-honmei"},
            {"num": "1 - 2 - 3", "tag": "本命", "style": "tag-honmei"},
            {"num": "1 - 4 - 3", "tag": "本命", "style": "tag-honmei"},
            {"num": "2 - 1 - 4", "tag": "狙い", "style": "tag-nerai"},
            {"num": "2 - 4 - 1", "tag": "狙い", "style": "tag-nerai"},
            {"num": "4 - 1 - 2", "tag": "穴", "style": "tag-ana"},
            {"num": "4 - 2 - 1", "tag": "穴", "style": "tag-ana"}
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
