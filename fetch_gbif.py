"""
從 GBIF 抓取台灣周圍魚種過去10年的分佈資料
範圍: 緯度 20-27°N, 經度 118-124°E
時間: 2016-2026
"""

import csv
import json
import re
import sys
import time
import urllib.request
import urllib.parse

GBIF_URL = "https://api.gbif.org/v1/occurrence/search"
OUT_FILE = "gbif_taiwan_fish.csv"

LAT_RANGE = "20,27"
LON_RANGE = "118,124"
YEAR_RANGE = "2016,2026"


def log(msg):
    print(msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"), flush=True)


def get_clean_species(csv_path):
    species = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            zh = row["target_zh"].strip()
            sci = row["scientificName"].strip().strip('"')
            # 去掉括號與括號後的作者資訊
            sci = sci.split("(")[0].strip()
            # 只保留前兩個單字（屬名+種名），去掉命名者
            parts = sci.split()
            if len(parts) >= 2:
                sci = parts[0] + " " + parts[1]
            else:
                sci = parts[0] if parts else ""
            # 排除 sp. / Gen. sp 等不明種
            if not sci or re.search(r'\bsp\b', sci, re.IGNORECASE) or "gen." in sci.lower():
                continue
            if sci not in species:
                species[sci] = zh
    return species


def fetch_species(sci_name, page_size=300, max_records=2000):
    records = []
    offset = 0
    retries = 3

    while offset < max_records:
        params = urllib.parse.urlencode({
            "scientificName": sci_name,
            "decimalLatitude": LAT_RANGE,
            "decimalLongitude": LON_RANGE,
            "year": YEAR_RANGE,
            "hasCoordinate": "true",
            "limit": page_size,
            "offset": offset,
        })
        url = f"{GBIF_URL}?{params}"

        for attempt in range(retries):
            try:
                req = urllib.request.urlopen(url, timeout=30)
                data = json.loads(req.read())
                break
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt * 2)
                else:
                    log(f"  SKIP {sci_name}: {e}")
                    return records

        results = data.get("results", [])
        total = data.get("count", 0)

        for r in results:
            records.append({
                "scientificName": r.get("scientificName", ""),
                "decimalLatitude": r.get("decimalLatitude"),
                "decimalLongitude": r.get("decimalLongitude"),
                "eventDate": r.get("eventDate", ""),
                "year": r.get("year"),
                "month": r.get("month"),
                "country": r.get("country", ""),
                "gbifID": r.get("gbifID", ""),
                "datasetName": r.get("datasetName", ""),
            })

        offset += len(results)
        if offset >= total or not results:
            break
        time.sleep(1)

    return records


def main():
    species_map = get_clean_species("sdm/occurrences.csv")
    log(f"Found {len(species_map)} valid species names")

    all_records = []
    fieldnames = [
        "target_zh", "scientificName", "decimalLatitude", "decimalLongitude",
        "eventDate", "year", "month", "country", "gbifID", "datasetName"
    ]

    for i, (sci, zh) in enumerate(species_map.items(), 1):
        log(f"[{i}/{len(species_map)}] {sci} ...")
        records = fetch_species(sci)
        for r in records:
            r["target_zh"] = zh
        all_records.extend(records)
        log(f"  -> {len(records)} records")
        time.sleep(1)

    with open(OUT_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    log(f"\nDone! Total {len(all_records)} records saved to {OUT_FILE}")
    build_fish_data_js(OUT_FILE)


def build_fish_data_js(csv_path, out_path="dashboard/fish_data.js"):
    records = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row["decimalLatitude"])
                lon = float(row["decimalLongitude"])
                month = int(row["month"]) if row["month"] else None
            except (ValueError, TypeError):
                continue
            if month is None:
                continue
            records.append({
                "zh": row["target_zh"],
                "sci": row["scientificName"],
                "lat": lat,
                "lon": lon,
                "year": int(row["year"]) if row["year"] else None,
                "month": month,
                "date": row["eventDate"][:10] if row["eventDate"] else "",
            })

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("const FISH_DATA = ")
        json.dump(records, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";")

    log(f"Built {out_path}  ({len(records)} records with month data)")


if __name__ == "__main__":
    main()
