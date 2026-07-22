"""抓取農業部「臺灣地區漁業資源保育區範圍」→ 解析出多邊形座標 → sdm/restricted_zones.json（航線規劃避開）。

來源：data.moa.gov.tw 開放資料（JSON，免金鑰），僅提供文字描述的「限制事項」欄位，
座標以 DMS 格式（如 24°36'16"N 120°43'23"E）夾雜點位標籤(A、B、C、D...)寫在文字裡，
沒有結構化多邊形欄位、格式也不統一（部分僅「低潮線向外延伸 200 公尺」等相對描述、無絕對座標）。

本腳本用 regex 從文字抓出 >=3 個座標點的記錄，依出現順序連成多邊形；抓不到/點數不足的
記錄**不硬猜**，印到 stdout 供人工抽查。人工確認後可手動整理成 sdm/restricted_zones_manual.json
（格式同輸出，見 ZoneRow），本腳本會自動合併進去（若檔案存在）。
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
URL = "https://data.moa.gov.tw/Service/OpenData/DataFileService.aspx?UnitId=729&IsTransData=1"
OUT = BASE / "sdm" / "restricted_zones.json"
MANUAL = BASE / "sdm" / "restricted_zones_manual.json"

# 一組 DMS 經緯度：24°36'16"N 120°43'23"E（緯度在前、經度在後，秒與雙引號可缺）
COORD_RE = re.compile(
    r"(\d{1,3})[°度](\d{1,2})[\'′分](\d{1,2}(?:\.\d+)?)?[\"″秒]?\s*([NS])"
    r"[,，、\s]*"
    r"(\d{1,3})[°度](\d{1,2})[\'′分](\d{1,2}(?:\.\d+)?)?[\"″秒]?\s*([EW])",
)


def dms_to_dd(deg: str, minute: str, sec: str | None, hemi: str) -> float:
    val = int(deg) + int(minute) / 60 + (float(sec) if sec else 0.0) / 3600
    return -val if hemi in ("S", "W") else val


def parse_polygon(text: str) -> list[list[float]] | None:
    points = []
    for m in COORD_RE.finditer(text):
        lat_d, lat_m, lat_s, lat_h, lon_d, lon_m, lon_s, lon_h = m.groups()
        lat = dms_to_dd(lat_d, lat_m, lat_s, lat_h)
        lon = dms_to_dd(lon_d, lon_m, lon_s, lon_h)
        points.append([round(lon, 5), round(lat, 5)])
    return points if len(points) >= 3 else None


def http_get_json(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> None:
    rows = http_get_json(URL)
    zones: list[dict] = []
    skipped: list[str] = []

    for r in rows:
        name = r.get("名稱") or r.get("name") or "(未命名)"
        text = r.get("限制事項") or r.get("限制事項　") or ""
        polygon = parse_polygon(text)
        if polygon is None:
            skipped.append(name)
            continue
        zones.append({
            "name": name,
            "county": r.get("縣市別", ""),
            "level": r.get("保護等級分類", ""),
            "polygon": polygon,
        })

    if MANUAL.exists():
        extra = json.loads(MANUAL.read_text(encoding="utf-8"))
        zones.extend(extra)
        print(f"併入人工整理檔 {MANUAL.name}：{len(extra)} 筆")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(zones, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"已產生 {OUT}　自動解析成功={len(zones) - (len(extra) if MANUAL.exists() else 0)}"
          f"　跳過(需人工確認)={len(skipped)}")
    if skipped:
        print("以下記錄無法自動解析出 >=3 個座標點，如需納入請人工查證後寫入 "
              f"{MANUAL.relative_to(BASE)}：")
        for name in skipped:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
