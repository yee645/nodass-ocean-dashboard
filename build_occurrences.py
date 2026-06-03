"""整併 TaiBIF／底拖／深海／博物館等生物調查資料，輸出物種分布模型(SDM)可用的出現點表。

來源（皆為 Darwin Core 類表格，本機既有，無需外部下載）：
  - 臺灣底拖與深海採集資料/*/*.csv
  - data/全球生物多樣性資料庫(TaiBIF)生物調查資料/*.csv,*.txt

處理：偵測 DwC 欄位 → 篩出目標商業魚種 → 限台灣海域框 → 跨檔去重。
輸出（sdm/）：
  - occurrences.csv：乾淨出現點表（species, lat, lon, date, depth, count, source...）。
  - species_counts.csv：各目標魚種筆數與建模充足度。
此步純本機完成，產出即「能建模的魚種池」。後續再接環境協變數(SST/葉綠素/水深)即可訓練 SDM。
"""
from __future__ import annotations

import csv
import glob
import re
from pathlib import Path

csv.field_size_limit(10 ** 7)

BASE = Path(__file__).resolve().parent
SRC_DIRS = [
    BASE / "臺灣底拖與深海採集資料",
    BASE / "data" / "全球生物多樣性資料庫(TaiBIF)生物調查資料",
]
OUT_DIR = BASE / "sdm"

# 台灣海域框（與儀表板網格一致）
LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = 117.0, 123.0, 20.0, 27.0

# 目標商業魚種（屬層級對應中文）；scientificName 首字（屬名）命中即收
GENUS_ZH = {
    # 表層洄游（儀表板魚種）
    "Coryphaena": "鬼頭刀", "Thunnus": "鮪屬", "Katsuwonus": "正鰹",
    "Euthynnus": "巴鰹", "Auxis": "圓花鰹", "Trichiurus": "白帶魚",
    "Scomber": "鯖(花飛)", "Cololabis": "秋刀魚", "Decapterus": "圓鰺",
    "Trachurus": "竹筴魚", "Uroteuthis": "鎖管(透抽)", "Loligo": "魷",
    "Sthenoteuthis": "魷", "Scomberomorus": "土魠(馬加鰆)",
    "Cypselurus": "飛魚", "Exocoetus": "飛魚", "Hirundichthys": "飛魚",
    "Cheilopogon": "飛魚", "Prognichthys": "飛魚",
    "Istiophorus": "雨傘旗魚", "Makaira": "黑皮旗魚", "Kajikia": "白皮旗魚",
    "Istiompax": "黑皮旗魚", "Xiphias": "劍旗魚",
    # 底棲經濟魚種
    "Nemipterus": "金線魚", "Upeneus": "日本緋鯉(秋姑)", "Parupeneus": "緋鯉",
    "Priacanthus": "大目鰱", "Saurida": "狗母魚", "Trachinocephalus": "狗母魚",
    "Pampus": "白鯧", "Larimichthys": "黃魚", "Pennahia": "叫姑魚",
    "Johnius": "叫姑魚", "Lutjanus": "笛鯛", "Epinephelus": "石斑",
    "Sphyraena": "魣(竹梭)", "Selar": "金帶花鯖", "Megalaspis": "扁甲鰺",
    "Evynnis": "赤鯮", "Dentex": "赤鯮", "Pagrus": "真鯛",
    "Branchiostegus": "方頭魚(馬頭)", "Mene": "眼眶魚",
}
FAMILY_ZH = {"Exocoetidae": "飛魚", "Istiophoridae": "旗魚"}


def sniff_delim(fh) -> str:
    s = fh.read(8192)
    fh.seek(0)
    return "\t" if s.count("\t") > s.count(",") else ","


def open_table(path: Path):
    """以 utf-8-sig 開啟，失敗則退回 cp950/big5。回傳 (rows, lower->原欄名)。"""
    for enc in ("utf-8-sig", "cp950", "big5"):
        try:
            fh = open(path, encoding=enc, newline="")
            delim = sniff_delim(fh)
            r = csv.DictReader(fh, delimiter=delim)
            rows = list(r)
            cols = {c.lower(): c for c in (r.fieldnames or [])}
            fh.close()
            return rows, cols
        except (UnicodeDecodeError, csv.Error):
            continue
    return [], {}


def num(s) -> float | None:
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def parse_date(s: str) -> tuple[str, str]:
    """回傳 (year, month)；無法解析則空字串。"""
    s = (s or "").strip()
    m = re.match(r"(\d{4})\D+(\d{1,2})", s)
    if m:
        mo = int(m.group(2))
        return m.group(1), (str(mo) if 1 <= mo <= 12 else "")
    m = re.match(r"(\d{4})", s)
    if m:
        return m.group(1), ""
    return "", ""


def target_label(sci: str) -> str | None:
    sci = (sci or "").strip()
    if not sci:
        return None
    genus = sci.split()[0]
    if genus in GENUS_ZH:
        return GENUS_ZH[genus]
    for fam, zh in FAMILY_ZH.items():
        if fam in sci:
            return zh
    return None


def col(cols, *names):
    for n in names:
        if n in cols:
            return cols[n]
    return None


def main() -> None:
    files = []
    for d in SRC_DIRS:
        files += [Path(p) for p in glob.glob(str(d / "**" / "*.csv"), recursive=True)]
        files += [Path(p) for p in glob.glob(str(d / "**" / "*.txt"), recursive=True)]

    records: list[dict] = []
    seen: set[tuple] = set()
    scanned = 0

    for f in files:
        rows, cols = open_table(f)
        if not rows:
            continue
        scanned += 1
        c_sci = col(cols, "scientificname", "species")
        c_lat = col(cols, "decimallatitude", "latitude", "lat")
        c_lon = col(cols, "decimallongitude", "longitude", "lon")
        c_date = col(cols, "eventdate", "date")
        c_cnt = col(cols, "individualcount", "count")
        c_dmax = col(cols, "maximumdepthinmeters")
        c_dmin = col(cols, "minimumdepthinmeters")
        c_dver = col(cols, "verbatimdepth")
        c_cls = col(cols, "class")
        c_ven = col(cols, "vernacularname")
        if not (c_sci and c_lat and c_lon):
            continue
        src = f.stem.replace("dwca-", "")
        for x in rows:
            sci = (x.get(c_sci) or "").strip()
            zh = target_label(sci)
            if zh is None:
                continue
            lat, lon = num(x.get(c_lat)), num(x.get(c_lon))
            if lat is None or lon is None:
                continue
            if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                continue
            date = (x.get(c_date) or "").strip() if c_date else ""
            year, mon = parse_date(date)
            key = (sci, round(lat, 3), round(lon, 3), date[:10])
            if key in seen:
                continue
            seen.add(key)
            depth = None
            for cc in (c_dmax, c_dmin, c_dver):
                if cc and num(x.get(cc)) is not None:
                    depth = num(x.get(cc))
                    break
            cnt = num(x.get(c_cnt)) if c_cnt else None
            records.append({
                "target_zh": zh,
                "scientificName": sci,
                "vernacularName": (x.get(c_ven) or "").strip() if c_ven else "",
                "class": (x.get(c_cls) or "").strip() if c_cls else "",
                "decimalLatitude": round(lat, 4),
                "decimalLongitude": round(lon, 4),
                "eventDate": date,
                "year": year,
                "month": mon,
                "depth_m": int(depth) if depth is not None else "",
                "individualCount": int(cnt) if cnt is not None else 1,
                "source": src,
            })

    # 併入已預先整理(含 target_zh)的 GBIF 出現點(近期 2016+，補足表層洄游魚種)
    for pf in [BASE / "data" / "gbif_taiwan_fish.csv"]:
        if not pf.exists():
            continue
        rows, cols = open_table(pf)
        c_zh = col(cols, "target_zh")
        c_sci = col(cols, "scientificname", "species")
        c_lat = col(cols, "decimallatitude", "latitude", "lat")
        c_lon = col(cols, "decimallongitude", "longitude", "lon")
        c_date = col(cols, "eventdate", "date")
        if not (c_zh and c_lat and c_lon):
            continue
        scanned += 1
        for x in rows:
            zh = (x.get(c_zh) or "").strip()
            lat, lon = num(x.get(c_lat)), num(x.get(c_lon))
            if not zh or lat is None or lon is None:
                continue
            if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                continue
            sci = (x.get(c_sci) or "").strip()
            date = (x.get(c_date) or "").strip() if c_date else ""
            year, mon = parse_date(date)
            key = (sci, round(lat, 3), round(lon, 3), date[:10])
            if key in seen:
                continue
            seen.add(key)
            records.append({
                "target_zh": zh, "scientificName": sci, "vernacularName": "",
                "class": "", "decimalLatitude": round(lat, 4),
                "decimalLongitude": round(lon, 4), "eventDate": date,
                "year": year, "month": mon, "depth_m": "",
                "individualCount": 1, "source": "GBIF",
            })

    OUT_DIR.mkdir(exist_ok=True)
    occ = OUT_DIR / "occurrences.csv"
    fields = ["target_zh", "scientificName", "vernacularName", "class",
              "decimalLatitude", "decimalLongitude", "eventDate", "year",
              "month", "depth_m", "individualCount", "source"]
    records.sort(key=lambda r: (r["target_zh"], r["scientificName"]))
    with open(occ, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(records)

    # 各目標魚種(屬層級中文)統計與建模充足度
    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "sp": set(), "src": set(), "mon": 0,
                               "years": set()})
    for r in records:
        a = agg[r["target_zh"]]
        a["n"] += 1
        a["sp"].add(r["scientificName"])
        a["src"].add(r["source"])
        if r["month"]:
            a["mon"] += 1
        if r["year"]:
            a["years"].add(r["year"])

    def sufficiency(n: int) -> str:
        return "充足(>=50)" if n >= 50 else ("可嘗試(30-49)" if n >= 30 else "偏少(<30)")

    counts = OUT_DIR / "species_counts.csv"
    with open(counts, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["目標魚種", "出現點數", "含物種數", "有年月筆數",
                    "年代範圍", "來源檔數", "建模充足度"])
        for zh, a in sorted(agg.items(), key=lambda kv: kv[1]["n"], reverse=True):
            yr = f"{min(a['years'])}-{max(a['years'])}" if a["years"] else "-"
            w.writerow([zh, a["n"], len(a["sp"]), a["mon"], yr,
                        len(a["src"]), sufficiency(a["n"])])

    # 主控台只輸出 ASCII，避免 Windows cp950 編碼錯誤；中文明細在 CSV
    ready = sum(1 for a in agg.values() if a["n"] >= 50)
    tryable = sum(1 for a in agg.values() if 30 <= a["n"] < 50)
    print(f"scanned files          : {scanned}")
    print(f"target occurrences     : {len(records)} (deduped)")
    print(f"target species-groups  : {len(agg)}")
    print(f"  model-ready (>=50)   : {ready}")
    print(f"  tryable   (30-49)    : {tryable}")
    print(f"  sparse    (<30)      : {len(agg) - ready - tryable}")
    print(f"wrote: {occ.relative_to(BASE)}")
    print(f"wrote: {counts.relative_to(BASE)}  (per-species detail, UTF-8)")


if __name__ == "__main__":
    main()
