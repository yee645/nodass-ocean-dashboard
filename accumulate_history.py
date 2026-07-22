"""每日累積 NODASS 開放浮標資料，逐步建立自有歷史以供模型訓練。

開放 API 每次僅回近兩日逐時資料；每天執行本程式即可去重累積，
數週後形成可訓練資料集（完全使用開放資料，符合競賽規定）。

用法：
    python accumulate_history.py
建議用 Windows 工作排程器每日執行一次（指令見 README 提示或對話說明）。
"""
from __future__ import annotations

import csv
import json
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent      # 專案根(相對於本檔)，取代舊硬編絕對路徑
HIST = DATA_DIR / "history.csv"
BASE = "https://nodass.namr.gov.tw/noapi/namr/v1"
STATION_FILES = ["stations_NAMR.json", "stations_CWA.json", "stations_IHMT.json"]

# 累積的核心欄位（時序模型用）
FIELDS = [
    "StationID", "time", "lat", "lon",
    "Wave_Height_Significant", "Wave_Maximum_Height",
    "Wave_Peak_Period", "Wave_Mean_Period",
    "Wind_Speed", "Wind_Gust_Speed", "Wind_Direction",
    "Air_Pressure", "Sea_Temperature", "Current_Speed",
]


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def load_fb_stations() -> list[dict]:
    out = []
    for fn in STATION_FILES:
        for s in json.loads((DATA_DIR / fn).read_text(encoding="utf-8")):
            if s.get("StationTypeID") == "FB":
                out.append(s)
    return out


def load_existing_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if HIST.exists():
        with HIST.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                keys.add((row["StationID"], row["time"]))
    return keys


def main() -> None:
    stations = load_fb_stations()
    today = date.today()
    d1 = (today - timedelta(days=2)).isoformat()
    d2 = today.isoformat()
    existing = load_existing_keys()
    new_rows: list[dict] = []

    for s in stations:
        sid = s["StationID"]
        url = f"{BASE}/obs/{sid}/data/?date1={d1}&date2={d2}"
        try:
            recs = json.loads(http_get(url))
            if not isinstance(recs, list):
                continue
            for r in recs:
                t = r.get("time")
                if not t or (sid, t) in existing:
                    continue
                row = {k: r.get(k) for k in FIELDS}
                row["StationID"] = sid
                row["time"] = t
                row["lat"] = s.get("CenterLatitude")
                row["lon"] = s.get("CenterLongitude")
                new_rows.append(row)
                existing.add((sid, t))
        except Exception as exc:  # noqa: BLE001
            print(f"  錯誤 {sid}: {exc}")
        time.sleep(0.3)

    write_header = not HIST.exists()
    with HIST.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(new_rows)

    total = len(load_existing_keys())
    print(f"本次新增 {len(new_rows)} 筆；累積總筆數 {total}（{HIST}）")


if __name__ == "__main__":
    main()
