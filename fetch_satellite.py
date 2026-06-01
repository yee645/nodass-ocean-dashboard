"""NODASS 開放衛星影像 API 介接(免 token)。

端點：/noapi/namr/v1/images/{ClassCode}?date1=&date2=
回傳每個場景的 bbox 與影像/圖例 URL(storage184.geonet.tw)。本模組負責列出與下載(快取)。
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = BASE / "_sat_cache"
API = "https://nodass.namr.gov.tw/noapi/namr/v1/images/{code}?date1={d1}&date2={d2}"
UA = {"User-Agent": "Mozilla/5.0"}


def _get(url: str, tries: int = 3) -> bytes:
    last = None
    for k in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=90).read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (k + 1))
    raise last


def list_scenes(code: str, d1: str, d2: str) -> list[dict]:
    return json.loads(_get(API.format(code=code, d1=d1, d2=d2)))


def bbox_of(rec: dict) -> tuple[float, float, float, float]:
    return (rec["WestBoundLongitude"], rec["EastBoundLongitude"],
            rec["SouthBoundLatitude"], rec["NorthBoundLatitude"])


def covers(rec: dict, target: tuple[float, float, float, float]) -> bool:
    w, e, s, n = bbox_of(rec)
    tw, te, ts, tn = target
    return not (e < tw or w > te or n < ts or s > tn)


def download(url: str) -> Path:
    """下載並快取(以檔名為鍵)，回傳本機路徑。"""
    CACHE.mkdir(exist_ok=True)
    name = url.rsplit("/", 1)[-1]
    p = CACHE / name
    if not (p.exists() and p.stat().st_size > 2000):
        p.write_bytes(_get(url))
        time.sleep(0.3)
    return p
