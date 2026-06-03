"""氣象署 OCM 海流模式 OPeNDAP 介接(公開、免授權)。

來源：中央氣象署 oceanapi OCM 模式，提供 0.025°(~2.5km)、未來 120 小時逐時預報，
變數含 SST(海溫)、UCURR/VCURR(東/北向海流)、SALT(鹽度)等，NetCDF 數值場。
本模組：尋找最新可用預報、以 OPeNDAP ascii 子集取小區數值場。
使用須註明來源：中央氣象署 OCM 海流模式。
"""
from __future__ import annotations

import datetime as dt
import urllib.parse
import urllib.request

import numpy as np

UA = {"User-Agent": "Mozilla/5.0"}
ROOT = "https://oceanapi.cwa.gov.tw/opendap/OCM"
LAT0, LON0, RES = 7.0, 109.0, 0.025      # 網格原點與解析度


def _get(url: str, timeout: int = 90) -> str:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read().decode("utf-8", "ignore")


def _exists(url: str) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read(64)
        return True
    except Exception:
        return False


def find_latest_init(back: int = 6) -> str | None:
    """回傳最新可用的預報起報日 YYYYMMDD（00Z）。"""
    today = dt.date.today()
    for k in range(back):
        d = (today - dt.timedelta(days=k)).strftime("%Y%m%d")
        if _exists(f"{ROOT}/{d}/00/9999/SST.{d}00.nc.dds"):
            return d
    return None


def base_url(init: str, var: str) -> str:
    return f"{ROOT}/{init}/00/9999/{var}.{init}00.nc"


def idx(lat_or_lon: float, origin: float) -> int:
    return int(round((lat_or_lon - origin) / RES))


def time_hours(init: str) -> np.ndarray:
    """回傳預報時間軸（小時，since 1800-01-01）。"""
    txt = _get(base_url(init, "SST") + ".ascii?time")
    line = [l for l in txt.splitlines() if l.startswith("time")][-1]
    return np.array([int(x) for x in line.split(",")[1:]], dtype=np.int64)


def hours_to_dt(h: int) -> dt.datetime:
    return dt.datetime(1800, 1, 1) + dt.timedelta(hours=int(h))


def subset(init: str, var: str, ti: int, bbox, stride: int = 2):
    """取單一時刻、小區的 2D 場。bbox=(west,east,south,north)。回傳 (lats, lons, arr)。"""
    w, e, s, n = bbox
    la0, la1 = idx(s, LAT0), idx(n, LAT0)
    lo0, lo1 = idx(w, LON0), idx(e, LON0)
    con = f"{var}[{ti}][0][{la0}:{stride}:{la1}][{lo0}:{stride}:{lo1}]"
    url = base_url(init, var) + ".ascii?" + urllib.parse.quote(con)
    txt = _get(url)
    lons, lats, rows = None, [], []
    for line in txt.splitlines():
        low = line.lower()
        if (".lon" in low) and ("," in line) and lons is None:
            lons = [float(x) for x in line.split(",")[1:] if x.strip()]
        elif f"{var}.{var}[" in line or (f".{var}[" in line and "lat=" in low):
            import re
            m = re.search(r"lat=([\-\d.]+)", line)
            if not m:
                continue
            lats.append(float(m.group(1)))
            vals = []
            for x in line.split(",")[1:]:
                x = x.strip()
                vals.append(np.nan if x in ("nan", "NaN", "-9999", "-9999.0") else float(x))
            rows.append(vals)
    arr = np.array(rows, dtype=np.float32)
    arr[arr <= -9990] = np.nan
    return np.array(lats), np.array(lons or []), arr


if __name__ == "__main__":
    init = find_latest_init()
    print("latest init:", init)
    th = time_hours(init)
    print("forecast steps:", len(th), "valid",
          hours_to_dt(th[0]).isoformat(), "->", hours_to_dt(th[-1]).isoformat())
    lats, lons, sst = subset(init, "SST", 0, (121.6, 123.4, 24.4, 26.2), stride=4)
    print("subset shape", sst.shape, "lat", lats[:3], "lon", lons[:3])
    print("SST valid range",
          round(float(np.nanmin(sst)), 2), "-", round(float(np.nanmax(sst)), 2),
          "valid cells", int(np.isfinite(sst).sum()))
