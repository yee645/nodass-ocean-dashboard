"""由 GBIF API 重抓台灣周邊海域目標經濟魚種出現點，輸出 data/gbif_taiwan_fish.csv。

公開、免金鑰(GBIF occurrence/search API)。供協作者重現出現點資料集，消除「資料斷層」。
流程：對每個目標屬/科 → GBIF 物種比對取 taxonKey → 以台灣周邊 WKT 多邊形 + 有座標查詢分頁取回。
產物可直接被 build_occurrences.py 併入（其已內建讀取 data/gbif_taiwan_fish.csv）。

用法：python fetch_occurrences.py
"""
from __future__ import annotations

import csv
import time
import urllib.parse
import urllib.request
from pathlib import Path

from build_occurrences import FAMILY_ZH, GENUS_ZH

BASE = Path(__file__).resolve().parent
OUT = BASE / "data" / "gbif_taiwan_fish.csv"
UA = {"User-Agent": "Mozilla/5.0"}
# 台灣周邊海域(含周邊海岸)WKT 多邊形：lon 118–124、lat 20–27
WKT = "POLYGON((118 20,124 20,124 27,118 27,118 20))"
PER_TAXON_CAP = 3000          # 每分類上限，避免過量下載
API = "https://api.gbif.org/v1"


def _get(url: str):
    import json
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=60).read())


def taxon_key(name: str, rank: str):
    q = urllib.parse.urlencode({"name": name, "rank": rank})
    m = _get(f"{API}/species/match?{q}")
    return m.get("usageKey") if m.get("matchType") != "NONE" else None


def fetch_taxon(key: int, zh: str) -> list[dict]:
    rows, offset = [], 0
    while offset < PER_TAXON_CAP:
        q = urllib.parse.urlencode({"taxonKey": key, "geometry": WKT,
                                    "hasCoordinate": "true", "limit": 300, "offset": offset})
        r = _get(f"{API}/occurrence/search?{q}")
        res = r.get("results", [])
        for o in res:
            lat, lon = o.get("decimalLatitude"), o.get("decimalLongitude")
            if lat is None or lon is None:
                continue
            ed = o.get("eventDate") or ""
            rows.append({
                "target_zh": zh,
                "scientificName": o.get("scientificName", ""),
                "decimalLatitude": round(lat, 5),
                "decimalLongitude": round(lon, 5),
                "eventDate": ed,
                "year": o.get("year") or (ed[:4] if ed[:4].isdigit() else ""),
                "month": o.get("month") or "",
                "country": o.get("country", ""),
                "gbifID": o.get("key", ""),
                "datasetName": o.get("datasetName", ""),
            })
        if r.get("endOfRecords") or not res:
            break
        offset += 300
        time.sleep(0.2)
    return rows


def main():
    targets = [(g, "GENUS") for g in GENUS_ZH] + [(f, "FAMILY") for f in FAMILY_ZH]
    seen, out = set(), []
    for name, rank in targets:
        zh = GENUS_ZH.get(name) or FAMILY_ZH.get(name)
        try:
            key = taxon_key(name, rank)
            if not key:
                print(f"  {name}: 無 taxonKey，略過")
                continue
            rows = fetch_taxon(key, zh)
            for r in rows:
                k = (r["scientificName"], r["decimalLatitude"], r["decimalLongitude"], r["eventDate"][:10])
                if k in seen:
                    continue
                seen.add(k)
                out.append(r)
            print(f"  {name} -> {zh}: {len(rows)} 筆")
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: 失敗 {type(e).__name__}")
        time.sleep(0.2)

    OUT.parent.mkdir(exist_ok=True)
    fields = ["target_zh", "scientificName", "decimalLatitude", "decimalLongitude",
              "eventDate", "year", "month", "country", "gbifID", "datasetName"]
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    print(f"完成：{len(out)} 筆(去重) -> {OUT.relative_to(BASE)}")
    print("接著執行 python build_occurrences.py 併入並更新 sdm/occurrences.csv")


if __name__ == "__main__":
    main()
