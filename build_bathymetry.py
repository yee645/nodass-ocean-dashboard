"""水深分級圖層：把 GEBCO 水深 GeoTIFF 轉成 web 端要吃的 sdm/depth_bands.json。

純 Python 處理，不需 QGIS/GDAL：
- GEBCO GeoTIFF 是規則經緯度網格，座標由 ModelPixelScaleTag + ModelTiepointTag 兩個
  tag 就能還原（EPSG:4326），用 tifffile 讀像素陣列即可，不需 rasterio/GDAL。
- 用 numpy 依深度門檻分級，skimage.measure.find_contours 對每一級的二值遮罩取
  0.5 等值線，效果等同 QGIS 的 polygonize+dissolve（同一分級天然合併成一輪廓）；
  skimage.measure.approximate_polygon 做 Douglas-Peucker 簡化，效果等同 QGIS 的
  Simplify，減少前端 point-in-polygon 要跑的頂點數。
- 降取樣(DOWNSAMPLE)取每個區塊的最淺點(depth 最小值)，故意保守，避免降解析度時
  把淺水區平均掉、讓吃水限制判斷失真。

輸入：`nodass.tif`（GEBCO bbox 匯出，使用者用官方 download.gebco.net 的 bbox 工具下載，
      無可程式化的公開 bbox API，需人工下載一次；水深是靜態資料，不需每次 build 重抓）。
輸出：`sdm/depth_bands.json`：[{name, minDepth, maxDepth, polygon:[[lon,lat],...]}]，
      本圖層是航線規劃參考用途，非精確航行圖，不支援多邊形內環(洞)。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import tifffile
from skimage.measure import approximate_polygon, find_contours

BASE = Path(__file__).resolve().parent
SRC = BASE / "nodass.tif"
OUT = BASE / "sdm" / "depth_bands.json"

BANDS = [(0, 20), (20, 50), (50, 100), (100, 200), (200, 12000)]  # 深度分級門檻(公尺)
DOWNSAMPLE = 4  # 15弧秒原始網格對航線規劃過細，降取樣減少多邊形頂點數
SIMPLIFY_TOL_DEG = 0.01  # Douglas-Peucker 容差，約 1 公里
MIN_POINTS = 4  # 簡化後少於這個點數視為雜訊，丟棄


def _load_depth() -> tuple[np.ndarray, float, float, float]:
    """回傳 (depth, lon0, lat0, scale)：depth[0,0] 對應 (lon0, lat0)（西南角），
    正值＝水深(公尺)，陸地/無資料設為 -1（分級門檻皆 >=0，天然被排除）。"""
    page = tifffile.TiffFile(SRC).pages[0]
    scale = float(page.tags["ModelPixelScaleTag"].value[0])
    tiepoint = page.tags["ModelTiepointTag"].value
    lon_topleft, lat_topleft = tiepoint[3], tiepoint[4]

    elevation = tifffile.imread(SRC).astype(np.float32)  # row0=北, col0=西
    elevation = np.flipud(elevation)  # row0=南，跟 lat 遞增方向一致
    lat0 = lat_topleft - (elevation.shape[0] - 1) * scale
    lon0 = lon_topleft

    depth = np.where(elevation < 0, -elevation, np.inf)  # 陸地設 +inf，降取樣取 min 時不會被選到
    if DOWNSAMPLE > 1:
        from skimage.measure import block_reduce

        depth = block_reduce(depth, (DOWNSAMPLE, DOWNSAMPLE), np.min)
        lon0 += (DOWNSAMPLE - 1) / 2 * scale
        lat0 += (DOWNSAMPLE - 1) / 2 * scale
        scale *= DOWNSAMPLE
    depth[np.isinf(depth)] = -1  # 整格皆陸地
    return depth, lon0, lat0, scale


def _band_polygons(mask: np.ndarray, lon0: float, lat0: float, scale: float) -> list[list[list[float]]]:
    polygons = []
    for contour in find_contours(mask.astype(np.float32), 0.5):
        simplified = approximate_polygon(contour, tolerance=SIMPLIFY_TOL_DEG / scale)
        if len(simplified) < MIN_POINTS:
            continue
        polygons.append([[round(lon0 + c * scale, 5), round(lat0 + r * scale, 5)] for r, c in simplified])
    return polygons


def main() -> None:
    if not SRC.exists():
        print(f"找不到 {SRC}，請先用 https://download.gebco.net 的 bbox 工具下載 GeoTIFF"
              f"（lon 117~123, lat 20~27），存成 {SRC.name}。")
        return

    depth, lon0, lat0, scale = _load_depth()
    bands = []
    for depth_min, depth_max in BANDS:
        mask = (depth >= depth_min) & (depth < depth_max)
        if not mask.any():
            continue
        for polygon in _band_polygons(mask, lon0, lat0, scale):
            bands.append({
                "name": f"{depth_min:g}-{depth_max:g}m",
                "minDepth": float(depth_min),
                "maxDepth": float(depth_max),
                "polygon": polygon,
            })

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(bands, ensure_ascii=False), encoding="utf-8")
    print(f"寫入 {OUT}，共 {len(bands)} 個等深帶多邊形")


if __name__ == "__main__":
    main()
