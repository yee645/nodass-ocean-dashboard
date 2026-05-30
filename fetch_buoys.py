"""抓取 NODASS 全台浮標站近兩日逐時資料（開放 API，無需授權）。

開放端點限制：單次查詢起始日需在「今天往前約 2 天」內，
完整歷史 /unlimited/ 需會員 access token。
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(r"D:\nodass")
OUT = DATA_DIR / "buoy_window.json"
BASE = "https://nodass.namr.gov.tw/noapi/namr/v1"
STATION_FILES = ["stations_NAMR.json", "stations_CWA.json", "stations_IHMT.json"]


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def load_fb_stations() -> list[dict]:
    stations: list[dict] = []
    for fn in STATION_FILES:
        data = json.loads((DATA_DIR / fn).read_text(encoding="utf-8"))
        stations += [s for s in data if s.get("StationTypeID") == "FB"]
    return stations


def main() -> None:
    today = date.today()
    d1 = (today - timedelta(days=2)).isoformat()
    d2 = today.isoformat()
    stations = load_fb_stations()
    print(f"抓取 {len(stations)} 個浮標站，區間 {d1} ~ {d2}")

    out: dict[str, dict] = {}
    for s in stations:
        sid = s["StationID"]
        url = f"{BASE}/obs/{sid}/data/?date1={d1}&date2={d2}"
        try:
            raw = http_get(url)
            recs = json.loads(raw)
            if not isinstance(recs, list):
                print(f"  跳過 {sid}: 非陣列回應")
                continue
            out[sid] = {
                "meta": {
                    "StationID": sid,
                    "StationName": s.get("StationName"),
                    "StationNameLocal": s.get("StationNameLocal"),
                    "Charge": s.get("StationChargeID"),
                    "lat": s.get("CenterLatitude"),
                    "lon": s.get("CenterLongitude"),
                },
                "records": recs,
            }
            print(f"  {sid:28} {len(recs):3} 筆")
        except Exception as exc:  # noqa: BLE001
            print(f"  錯誤 {sid}: {exc}")
        time.sleep(0.3)

    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"已寫出 {OUT}  站數={len(out)}")


if __name__ == "__main__":
    main()
