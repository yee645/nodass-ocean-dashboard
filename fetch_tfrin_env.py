"""爬取水產試驗所「臺灣周邊海域漁場環境資料」(tfrin.gov.tw id=70)，
解析逐月航次 PDF（文字型表格）為乾淨數值資料表，作為 SDM 環境協變數來源。

資料皆為水試所公開發布，使用須註明出處（水產試驗所），不需另外申請。
兩類記錄：
  溫鹽分布(TS) ：Station/Date/Time/Lat/Lon/Depth/Temperature(°C)/Salinity(psu)，含多深度剖面。
  葉綠素分布(CHL)：Station/Date/Time/Lat/Lon/Depth/MaxSamplingDepth/Chl-a>10μm/Chl-a<10μm。
輸出：sdm/tfrin_env.csv
"""
from __future__ import annotations

import csv
import html as ht
import re
import time
import urllib.request
from pathlib import Path

import fitz  # PyMuPDF

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "sdm"
PDF_CACHE = BASE / "_tfrin_pdf"          # 已下載 PDF 快取，供續傳（_ 前綴已被 gitignore 規則排除）
LIST_URL = "https://www.tfrin.gov.tw/ws.php?id=70&page={}"
REC_URL = "https://www.tfrin.gov.tw/ws.php?id={}"
SITE = "https://www.tfrin.gov.tw/"
UA = {"User-Agent": "Mozilla/5.0"}

DATE_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}")
INT_RE = re.compile(r"^\d+$")


def fetch(url: str, tries: int = 4) -> bytes:
    """帶退避重試的下載；tfrin 對爆量請求會以 404/HTTPError 限流，放慢即可恢復。"""
    last = None
    for k in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as e:  # noqa: BLE001 (含 HTTPError/URLError/timeout)
            last = e
            time.sleep(5 * (k + 1) + 5)  # 10,15,20,25s 退避
    raise last


def list_records() -> dict[str, str]:
    """掃 6 頁清單，回傳 {record_id: title}。"""
    recs: dict[str, str] = {}
    for pg in range(1, 7):
        try:
            html = fetch(LIST_URL.format(pg)).decode("utf-8", "ignore")
        except Exception:
            continue
        for rid, title in re.findall(r"ws\.php\?id=(\d+)[^>]*>([^<]+)<", html):
            title = title.strip()
            if rid != "70" and ("溫鹽" in title or "葉綠" in title):
                recs[rid] = title
    return recs


def record_pdf_url(rid: str) -> str | None:
    html = fetch(REC_URL.format(rid)).decode("utf-8", "ignore")
    m = re.search(r"redirect_files\.php\?[^\"' >]+", html)
    return SITE + ht.unescape(m.group(0)) if m else None


def ym_from_title(title: str) -> tuple[str, str]:
    m = re.search(r"(\d{4})[.\-/](\d{1,2})", title)
    return (m.group(1), str(int(m.group(2)))) if m else ("", "")


def parse_pdf(data: bytes, kind: str) -> list[dict]:
    """以「站號(整數)＋日期」為記錄起點，每筆取 8 行，依類別對應欄位。"""
    doc = fitz.open(stream=data, filetype="pdf")
    lines = [l.strip() for l in
             "\n".join(p.get_text() for p in doc).splitlines() if l.strip()]
    rows: list[dict] = []
    i, n = 0, len(lines)
    while i < n - 7:
        if INT_RE.match(lines[i]) and DATE_RE.match(lines[i + 1]):
            b = lines[i:i + 8]
            try:
                if kind == "TS":      # st,date,time,lat,lon,depth,temp,sal
                    lat, lon, depth, temp, sal = (float(b[3]), float(b[4]),
                                                  float(b[5]), float(b[6]), float(b[7]))
                    rec = {"depth_m": depth, "temperature_c": temp,
                           "salinity_psu": sal, "chl_gt10": "", "chl_lt10": ""}
                else:                 # st,datetime,lat,lon,depth,maxdep,chl1,chl2
                    lat, lon, depth = float(b[2]), float(b[3]), float(b[4])
                    rec = {"depth_m": depth, "temperature_c": "", "salinity_psu": "",
                           "chl_gt10": float(b[6]), "chl_lt10": float(b[7])}
                if not (19 <= lat <= 28 and 116 <= lon <= 125):
                    raise ValueError
                rec.update({"station": b[0], "date": b[1],
                            "lat": round(lat, 4), "lon": round(lon, 4)})
                rows.append(rec)
                i += 8
                continue
            except (ValueError, IndexError):
                pass
        i += 1
    return rows


def main() -> None:
    recs = list_records()
    print(f"records listed: {len(recs)}")
    OUT_DIR.mkdir(exist_ok=True)
    PDF_CACHE.mkdir(exist_ok=True)
    fields = ["kind", "year", "month", "station", "date", "lat", "lon",
              "depth_m", "temperature_c", "salinity_psu", "chl_gt10",
              "chl_lt10", "record_id"]
    all_rows: list[dict] = []
    ok = fail = 0
    for rid, title in sorted(recs.items(), key=lambda x: int(x[0])):
        kind = "TS" if "溫鹽" in title else "CHL"
        year, month = ym_from_title(title)
        pdf_path = PDF_CACHE / f"{rid}.pdf"
        try:
            if pdf_path.exists() and pdf_path.stat().st_size > 1000:
                data = pdf_path.read_bytes()           # 續傳：用快取
            else:
                url = record_pdf_url(rid)
                if not url:
                    fail += 1
                    print(f"  [{rid}] no-pdf")
                    continue
                data = fetch(url)
                pdf_path.write_bytes(data)
                time.sleep(1.5)                        # 僅在實際下載後放慢
            rows = parse_pdf(data, kind)
            for r in rows:
                r.update({"kind": kind, "year": year, "month": month,
                          "record_id": rid})
                all_rows.append(r)
            ok += 1
            print(f"  [{rid}] {kind} {year}.{month}: {len(rows)} rows")
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"  [{rid}] FAIL {type(e).__name__}")

    with open(OUT_DIR / "tfrin_env.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r.get(k, "") for k in fields})

    ts = sum(1 for r in all_rows if r["kind"] == "TS")
    chl = sum(1 for r in all_rows if r["kind"] == "CHL")
    print(f"done: records ok={ok} fail={fail}; rows TS={ts} CHL={chl} "
          f"total={len(all_rows)} -> sdm/tfrin_env.csv")


if __name__ == "__main__":
    main()
