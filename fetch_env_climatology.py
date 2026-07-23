"""現在頁多協變數 SDM 用環境氣候場（issue #10）：水深(靜態) + 逐月 SST/鹽度氣候場 + 逐月葉綠素氣候場。

動機：build_sdm_now.py 原本用「今日即時 SST 快照」當全部歷史出現點(1945–2026)的環境特徵，
等於拿今天的水溫套在幾十年前的紀錄上，環境-出現配對本身就是錯的，AUC 只有 0.54–0.67。
本檔改抓「氣候場」——SST/鹽度/葉綠素在每個月份的多年平均，讓 3 月的出現點配 3 月氣候、
7 月的配 7 月氣候，時間對得上；水深是靜態的，對底棲/近岸魚種是關鍵協變數。

資料來源(皆公開、免金鑰，OPeNDAP 可直接框 bbox，不需整檔下載)：
  水深   NOAA CoastWatch ERDDAP griddap `etopo180`(ETOPO1, ~0.0167°)
  SST/鹽度 NOAA NCEI THREDDS OPeNDAP `woa23_decav_{t|s}{MM}_04.nc`(WOA23, 0.25°, 標準月氣候場)
  葉綠素 NOAA CoastWatch ERDDAP griddap `erdMH1chlamday`(MODIS Aqua 月合成，2003–2022；
         逐月氣候平均 = 同月份取多年平均，作法與 build_forecast.py 的 GOCI 氣候平均一致)

輸出：`_env_cache/*.json`(原生解析度、逐月快取，gitignore)，供 build_sdm_now.py 用最近格點查詢
（不重取樣成固定網格，保留各資料源原生精度、也省去插值誤差)。
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
CACHE = BASE / "_env_cache"
CACHE.mkdir(exist_ok=True)

# 現在頁網格 bbox(對齊 build_fishing.py 的 GRID_STEP 範圍)
BBOX = {"lat0": 20.0, "lat1": 27.0, "lon0": 117.0, "lon1": 123.0}
CHL_YEARS = list(range(2010, 2022))  # MODIS Aqua chlor_a 月合成資料 2022-03 後停更，取近 12 年氣候平均
MAX_CHL_YEARS_PER_MONTH = 10         # 每月最多取幾年平均，避免請求過多逾時


def _get(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _cached(name: str, fetch_fn) -> dict:
    path = CACHE / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch_fn()
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return data


def fetch_etopo_depth() -> dict:
    """靜態水深：ETOPO1 高程(m，陸正海負)，轉水深(m，海為正、陸地記 0)。stride=2 降取樣減少傳輸量。"""
    def _fetch() -> dict:
        url = (
            "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv?altitude"
            f"%5B({BBOX['lat0']}):2:({BBOX['lat1']})%5D%5B({BBOX['lon0']}):2:({BBOX['lon1']})%5D"
        )
        txt = _get(url)
        lats, lons, depths = [], [], []
        for line in txt.splitlines()[2:]:
            parts = line.split(",")
            if len(parts) != 3:
                continue
            lat, lon, alt = float(parts[0]), float(parts[1]), float(parts[2])
            lats.append(lat)
            lons.append(lon)
            depths.append(max(0.0, -alt))
        print(f"  ETOPO 水深：{len(lats)} 點")
        return {"lat": lats, "lon": lons, "depth": depths}
    return _cached("etopo_depth", _fetch)


def fetch_woa_month(month: int, var: str) -> dict:
    """WOA23 月氣候場(表層，depth=0)：var='t'(海溫) 或 's'(鹽度)。"""
    def _fetch() -> dict:
        mm = f"{month:02d}"
        fname = f"woa23_decav_{var}{mm}_04.nc"
        base = f"https://www.ncei.noaa.gov/thredds-ocean/dodsC/woa23/DATA/{'temperature' if var == 't' else 'salinity'}/netcdf/decav/0.25/{fname}"
        # 0.25° 網格：index = round((value - origin) / 0.25)，lon 為 -180~180、lat 為 -90~90
        lo0 = round((BBOX["lon0"] + 179.875) / 0.25)
        lo1 = round((BBOX["lon1"] + 179.875) / 0.25)
        la0 = round((BBOX["lat0"] + 89.875) / 0.25)
        la1 = round((BBOX["lat1"] + 89.875) / 0.25)
        varname = f"{var}_an"
        url = (
            f"{base}.ascii?{varname}%5B0:1:0%5D%5B0:1:0%5D"
            f"%5B{la0}:1:{la1}%5D%5B{lo0}:1:{lo1}%5D"
        )
        txt = _get(url, timeout=90)
        lats = [round(-89.875 + i * 0.25, 4) for i in range(la0, la1 + 1)]
        lons = [round(-179.875 + j * 0.25, 4) for j in range(lo0, lo1 + 1)]
        grid: list[list[float | None]] = []
        for line in txt.splitlines():
            if not line.startswith(f"[0][0]["):
                continue
            vals = line.split(",")[1:]
            row = [None if float(v) > 1e30 else round(float(v), 4) for v in vals]
            grid.append(row)
        print(f"  WOA23 {'SST' if var == 't' else '鹽度'} {mm} 月：{len(grid)}x{len(lons)} 格")
        return {"lat": lats, "lon": lons, "grid": grid}
    return _cached(f"woa_{var}_{month:02d}", _fetch)


def fetch_chl_month_climatology(month: int) -> dict:
    """MODIS Aqua chlor_a 逐月氣候平均：同月份取多年(CHL_YEARS)平均，nanmean 忽略缺測/雲遮。"""
    def _fetch() -> dict:
        years = CHL_YEARS[-MAX_CHL_YEARS_PER_MONTH:]
        stack: list[np.ndarray] = []
        lats = lons = None
        for yr in years:
            url = (
                "https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMH1chlamday.csv?chlorophyll"
                f"%5B({yr}-{month:02d}-16T00:00:00Z)%5D"
                f"%5B({BBOX['lat0']}):({BBOX['lat1']})%5D%5B({BBOX['lon0']}):({BBOX['lon1']})%5D"
            )
            try:
                txt = _get(url, timeout=60)
            except Exception:
                continue
            rows_lat: list[float] = []
            rows_lon: list[float] = []
            vals: list[float] = []
            for line in txt.splitlines()[2:]:
                parts = line.split(",")
                if len(parts) != 4:
                    continue
                try:
                    lat, lon, v = float(parts[1]), float(parts[2]), float(parts[3])
                except ValueError:
                    continue
                rows_lat.append(lat)
                rows_lon.append(lon)
                vals.append(v)
            if not vals:
                continue
            if lats is None:
                lats, lons = rows_lat, rows_lon
            if len(vals) == len(lats):
                stack.append(np.array(vals, dtype=float))
        if not stack:
            print(f"  MODIS 葉綠素 {month:02d} 月：無可用資料")
            return {"lat": [], "lon": [], "chl": []}
        mean = np.nanmean(np.stack(stack), axis=0)
        print(f"  MODIS 葉綠素 {month:02d} 月氣候平均：{len(stack)} 年、{len(mean)} 點")
        return {"lat": lats, "lon": lons, "chl": [None if not np.isfinite(v) else round(float(v), 4) for v in mean]}
    return _cached(f"chl_clim_{month:02d}", _fetch)


def build_all() -> None:
    print("== 水深 ==")
    fetch_etopo_depth()
    for m in range(1, 13):
        print(f"== 第 {m} 月 ==")
        fetch_woa_month(m, "t")
        fetch_woa_month(m, "s")
        fetch_chl_month_climatology(m)
    print("完成，快取於", CACHE)


if __name__ == "__main__":
    build_all()
