"""水深資料處理：把本機 GEBCO 水深網格重取樣成航線規劃用的 0.05° 格網（第二層水深限制）。

GEBCO 沒有可直接用經緯度 bbox 打的公開 API（OPeNDAP 走 CEDA，需帳號），改採「人工下載一次、
程式在地處理」——比照本專案 data/ 原始生物資料的既有慣例（見 CLAUDE.md）：

  1. 開 https://download.gebco.net/ ，用內建 bounding box 工具框台灣周邊海域
     （建議 lon 117~123、lat 20~27），格式選 **Esri ASCII raster (.asc)**
     （純文字格式，免額外套件即可解析；不要選 netCDF，需要 netCDF4 套件）。
  2. 下載後把 .asc 檔放到 `_bathy_cache/gebco.asc`（此資料夾已 gitignore）。
  3. 執行 `python build_bathymetry.py`，輸出 `sdm/bathymetry.json`。

水深是靜態資料，只需做一次（除非要換更高解析度來源），不需排進 setup.sh / live_update.py。
輸出網格原點/步進對齊 `build_fishing.py` 的 GRID_STEP，供前端航線規劃依經緯度直接對齊查表。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from dashboard_common import on_land

BASE = Path(__file__).resolve().parent
SRC = BASE / "_bathy_cache" / "gebco.asc"
OUT = BASE / "sdm" / "bathymetry.json"

GRID_STEP = 0.05      # 需與 build_fishing.py 的 GRID_STEP 一致，確保前端對齊查表
LAT0, LAT1 = 20.0, 27.0
LON0, LON1 = 117.0, 123.0


def read_esri_ascii(path: Path):
    """讀 Esri ASCII Grid（GEBCO bbox 下載工具輸出格式）。回傳 (values, xll, yll, cellsize, nodata)。"""
    with path.open("r", encoding="utf-8") as f:
        header = {}
        for _ in range(6):
            key, val = f.readline().split()
            header[key.lower()] = val
        ncols = int(header["ncols"])
        nrows = int(header["nrows"])
        xll = float(header.get("xllcorner", header.get("xllcenter")))
        yll = float(header.get("yllcorner", header.get("yllcenter")))
        cellsize = float(header["cellsize"])
        nodata = float(header.get("nodata_value", -9999))
        values = np.loadtxt(f, dtype=np.float32).reshape(nrows, ncols)
    return values, xll, yll, cellsize, nodata


def main() -> None:
    if not SRC.exists():
        print(f"找不到 {SRC}，請先依本檔開頭說明手動下載 GEBCO bbox（Esri ASCII 格式）")
        return

    values, xll, yll, cellsize, nodata = read_esri_ascii(SRC)
    nrows, ncols = values.shape
    top_lat = yll + (nrows - 1) * cellsize   # row 0 = 最北（Esri ASCII 由北到南存列）

    cells = []
    lat = LAT0
    while lat <= LAT1:
        lon = LON0
        while lon <= LON1:
            if not on_land(lon, lat):
                row = int(round((top_lat - lat) / cellsize))
                col = int(round((lon - xll) / cellsize))
                if 0 <= row < nrows and 0 <= col < ncols:
                    elev = float(values[row, col])
                    if elev != nodata and elev < 0:   # 只留海域(高程<0)，陸地已由 coast mask 處理
                        cells.append({
                            "lat": round(lat, 3), "lon": round(lon, 3),
                            "depth": round(-elev, 1),   # 正值水深(公尺)
                        })
            lon += GRID_STEP
        lat += GRID_STEP

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps({"step": GRID_STEP, "cells": cells}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"已產生 {OUT}　格點數={len(cells)}（來源網格 {ncols}x{nrows}, cellsize={cellsize}°）")


if __name__ == "__main__":
    main()
