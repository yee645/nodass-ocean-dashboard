"""衛星色彩影像數位化：用圖例色帶建查找表(LUT)，把 NODASS 開放衛星影像
(JPEG，jet 色帶 + 已知數值範圍)反推成數值，並依 bbox 做地理定位。

NODASS images 端點為開放資料(免 token)，回傳影像含精確 bbox 與圖例，
故可數位化為高解析(~1km)數值網格，遠細於浮標內插。
"""
from __future__ import annotations

import numpy as np
from PIL import Image


def _read_rgb(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def legend_lut(legend_path: str, vmin: float, vmax: float, scale: str = "linear",
               n: int = 256) -> tuple[np.ndarray, np.ndarray]:
    """從圖例色帶取出 (LUT_rgb, LUT_val)。

    自動偵測色帶列(彩度最高、連續最長的水平帶)，沿 x 取樣 n 點，
    依 scale 將位置映射為數值。
    """
    img = _read_rgb(legend_path)
    chroma = img.max(axis=2) - img.min(axis=2)
    colorful = chroma > 40
    # 取彩色像素最多的列為色帶列
    row = int(colorful.sum(axis=1).argmax())
    xs = np.where(colorful[row])[0]
    x0, x1 = int(xs.min()), int(xs.max())
    pos = np.linspace(0.0, 1.0, n)
    px = (x0 + pos * (x1 - x0)).astype(int)
    lut_rgb = img[row, px, :]                       # n×3
    if scale == "log":
        lo, hi = np.log10(vmin), np.log10(vmax)
        lut_val = 10 ** (lo + pos * (hi - lo))
    else:
        lut_val = vmin + pos * (vmax - vmin)
    return lut_rgb, lut_val


def invert(rgb: np.ndarray, lut_rgb: np.ndarray, lut_val: np.ndarray,
           max_dist: float = 45.0) -> np.ndarray:
    """將 RGB 陣列(...×3)以最近色帶色反推為數值；離色帶過遠者回 NaN(無資料/陸地/雲)。"""
    flat = rgb.reshape(-1, 3)
    # 對每個像素找最近 LUT 色（分塊避免記憶體爆量）
    out = np.empty(flat.shape[0], dtype=np.float32)
    dist = np.empty(flat.shape[0], dtype=np.float32)
    step = 20000
    for i in range(0, flat.shape[0], step):
        chunk = flat[i:i + step][:, None, :]        # k×1×3
        d = np.sqrt(((chunk - lut_rgb[None, :, :]) ** 2).sum(axis=2))  # k×n
        j = d.argmin(axis=1)
        out[i:i + step] = lut_val[j]
        dist[i:i + step] = d[np.arange(len(j)), j]
    out[dist > max_dist] = np.nan
    return out.reshape(rgb.shape[:2])


def sample_grid(image_path: str, bbox: tuple[float, float, float, float],
                lut_rgb, lut_val, lats: np.ndarray, lons: np.ndarray,
                max_dist: float = 45.0) -> np.ndarray:
    """在指定 lat/lon 取樣影像數值(向量化)。bbox=(west,east,south,north)。"""
    img = _read_rgb(image_path)
    h, w = img.shape[:2]
    west, east, south, north = bbox
    py = np.round((north - lats) / (north - south) * (h - 1)).astype(int)
    px = np.round((lons - west) / (east - west) * (w - 1)).astype(int)
    okx = (px >= 0) & (px < w)
    oky = (py >= 0) & (py < h)
    pyc = np.clip(py, 0, h - 1)
    pxc = np.clip(px, 0, w - 1)
    rgb = img[pyc[:, None], pxc[None, :], :]            # Ny×Nx×3
    vals = invert(rgb, lut_rgb, lut_val, max_dist)
    vals[~oky[:, None] | ~okx[None, :]] = np.nan
    return vals


# 各 ClassCode 的圖例數值範圍與刻度（由圖例標註讀得）
LEGEND_SPEC = {
    "SLNT_S3_SST": {"vmin": 0.0, "vmax": 30.0, "scale": "linear"},   # °C
    "GOCI_CHL": {"vmin": 0.001, "vmax": 35.0, "scale": "log"},        # mg/m3
    "OLNT_S3_CHL": {"vmin": 0.001, "vmax": 35.0, "scale": "log"},
}
