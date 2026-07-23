"""現在頁第一層(L1) 機器學習 SDM 訓練器 v2（issue #10：多協變數 + 氣候場，取代弱版）。

v1 的根本問題：環境特徵(sst/front/cur)全部取自「今日即時 IDW 快照」，卻套用在 1945–2026
全部歷史出現點上——等於拿今天的水溫去配幾十年前的紀錄，環境-出現配對本身就是錯的，
才會出現「東部魚種(如飛魚)高分區被拉去西部」這類問題，AUC 也只有 0.54–0.67。

v2 改用「氣候場」：出現點依「自己的月份」去查該月份的多年平均環境(SST/鹽度/葉綠素氣候平均)，
時間才對得上；另加水深(靜態，對底棲/近岸魚種是關鍵協變數，過去被完全忽略)。

資料(見 fetch_env_climatology.py，皆公開免金鑰，用快取避免重複抓取)：
  水深(ETOPO)、SST/鹽度氣候場(WOA23)、葉綠素氣候平均(MODIS Aqua chlor_a)。

特徵(每點，依該點自己的月份查氣候場；欄序見 FEAT)：
  sst_clim, sst_clim², sal_clim, log(chl_clim), front_clim(|∇SST_clim|), log(depth+1), sin(2π·m/12), cos(2π·m/12)
  （v1 的 cur 已移除：海流沒有氣候場資料源，historically 同樣是「今日快照套歷史」的錯誤配對）

去偏：同 v1，target-group 背景(焦點魚種以外的全體出現點)修正採樣/作業努力偏差。
驗證：空間分塊交叉驗證(0.5° 棋盤分塊, 4 折) AUC + Boyce index(簡化版：預測值域切 bins，
      每 bin 的 presence/background 密度比對 bin 序做 Spearman，越接近 1 代表預測單調可信)。

推論建議(前端或後續管線)：sst 用「今日即時值」(比氣候平均更準)，sal/chl/depth 用氣候場
(無即時來源，氣候平均是次佳選擇)——即 meta.infer_note 所述，本檔僅訓練係數，不含推論介面。

輸出：sdm/sdm_now.json（結構同 v1，另加 boyce 欄位）
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.optimize import minimize

import fetch_env_climatology as ENV
from species_traits import SPECIES as TRAITS

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
SDM = BASE / "sdm"
MODEL_MIN = 12          # 建模所需最少落網格的出現點
L2 = 0.05               # logistic L2 正則(標準化特徵空間)
BG_PER_PRES = 8         # 背景點數 = presence 數 × 此值
BG_CAP = 1500           # 背景點數上限
CV_FOLDS = 4
BLOCK_DEG = 0.5         # 空間分塊邊長
FEAT = ["sst_clim", "sst_clim2", "sal_clim", "log_chl", "front_clim", "log_depth", "sin_m", "cos_m"]
RNG = np.random.default_rng(20260606)
CHL_FLOOR = 0.02        # log 前下限(mg/m3)，避免 log(0)

# 儀表板魚種名 → 出現點 target_zh 標籤集合（鮪屬無法分離黑鮪/黃鰭鮪→留空視為不足）。
SPECIES_MAP: dict[str, set[str]] = {
    "鬼頭刀": {"鬼頭刀"},
    "太平洋黑鮪": set(),
    "黃鰭鮪": set(),
    "正鰹": {"正鰹"},
    "白帶魚": {"白帶魚"},
    "白腹鯖(花飛)": {"鯖(花飛)"},
    "秋刀魚": {"秋刀魚"},
    "旗魚": {"旗魚", "雨傘旗魚", "黑皮旗魚", "白皮旗魚", "劍旗魚"},
    "飛魚": {"飛魚"},
    "鎖管(透抽)": set(),
}


# --- 氣候場：重排成規則網格 + 最近格查詢 ------------------------------------

def _reshape_flat(lat_flat, lon_flat, val_flat):
    """把 CSV 攤平的 (lat,lon,val) 三條列重排成規則 2D 網格 grid[i][j]，i/j 對應遞增排序的 lat/lon 軸。"""
    lats = sorted(set(round(x, 6) for x in lat_flat))
    lons = sorted(set(round(x, 6) for x in lon_flat))
    lat_idx = {v: i for i, v in enumerate(lats)}
    lon_idx = {v: i for i, v in enumerate(lons)}
    grid: list[list[float | None]] = [[None] * len(lons) for _ in range(len(lats))]
    for la, lo, v in zip(lat_flat, lon_flat, val_flat):
        grid[lat_idx[round(la, 6)]][lon_idx[round(lo, 6)]] = v
    return lats, lons, grid


def _fill_gaps(grid: list[list[float | None]]) -> np.ndarray:
    """最近有效值補洞 + 輕度平滑，處理雲遮/資料缺口(同 build_forecast.py 的葉綠素補洞手法)。"""
    arr = np.array([[np.nan if v is None else v for v in row] for row in grid], dtype=float)
    mask = np.isfinite(arr)
    if not mask.any():
        return arr
    idx = ndimage.distance_transform_edt(~mask, return_distances=False, return_indices=True)
    filled = arr[tuple(idx)]
    return ndimage.gaussian_filter(filled, sigma=1.0)


def _lookup_fn(lat_axis: list[float], lon_axis: list[float], grid: np.ndarray):
    lat0, dlat = lat_axis[0], lat_axis[1] - lat_axis[0]
    lon0, dlon = lon_axis[0], lon_axis[1] - lon_axis[0]
    nlat, nlon = len(lat_axis), len(lon_axis)

    def query(lat: float, lon: float) -> float | None:
        i = int(round((lat - lat0) / dlat))
        j = int(round((lon - lon0) / dlon))
        if 0 <= i < nlat and 0 <= j < nlon:
            v = grid[i][j]
            return None if (isinstance(v, float) and math.isnan(v)) else float(v)
        return None
    return query


def _front_from_grid(lat_axis, lon_axis, grid: np.ndarray) -> np.ndarray:
    """|∇SST_clim|：對氣候場網格做中央差分(度為單位的簡化梯度，與現有 front 定義一致)。"""
    gy, gx = np.gradient(grid)
    return np.hypot(gx, gy)


class MonthEnv:
    """單一月份的氣候場查詢器：sst/sal/chl/front 皆為 (lat,lon)->float|None 的查詢函式。"""

    def __init__(self, month: int):
        t = ENV.fetch_woa_month(month, "t")
        s = ENV.fetch_woa_month(month, "s")
        c = ENV.fetch_chl_month_climatology(month)

        # WOA 0.25° 對台灣海岸線太粗，近岸格常被判成陸地(NaN)；比照葉綠素做最近值補洞，
        # 避免近岸出現點(標本/卸魚紀錄多集中在近岸)因最近格剛好落陸地而被整點丟棄。
        t_grid = _fill_gaps([[np.nan if v is None else v for v in row] for row in t["grid"]])
        s_grid = _fill_gaps([[np.nan if v is None else v for v in row] for row in s["grid"]])
        self.sst = _lookup_fn(t["lat"], t["lon"], t_grid)
        self.sal = _lookup_fn(s["lat"], s["lon"], s_grid)
        self.front = _lookup_fn(t["lat"], t["lon"], _front_from_grid(t["lat"], t["lon"], t_grid))

        if c["lat"]:
            c_lats, c_lons, c_grid = _reshape_flat(c["lat"], c["lon"], c["chl"])
            self.chl = _lookup_fn(c_lats, c_lons, _fill_gaps(c_grid))
        else:
            self.chl = lambda lat, lon: None


def load_env() -> tuple[dict[int, MonthEnv], object]:
    print("載入環境氣候場(水深 + 12 個月 SST/鹽度/葉綠素)...")
    depth_raw = ENV.fetch_etopo_depth()
    d_lats, d_lons, d_grid = _reshape_flat(depth_raw["lat"], depth_raw["lon"], depth_raw["depth"])
    depth_fn = _lookup_fn(d_lats, d_lons, _fill_gaps(d_grid))
    months = {m: MonthEnv(m) for m in range(1, 13)}
    return months, depth_fn


def snap_env(months: dict[int, MonthEnv], depth_fn, lat: float, lon: float, month: int) -> dict | None:
    env = months[month]
    sst = env.sst(lat, lon)
    if sst is None:
        return None
    sal = env.sal(lat, lon)
    chl = env.chl(lat, lon)
    front = env.front(lat, lon)
    depth = depth_fn(lat, lon)
    if sal is None or chl is None or front is None or depth is None:
        return None
    return {"sst": sst, "sal": sal, "chl": chl, "front": front, "depth": depth}


def load_points(months: dict[int, MonthEnv], depth_fn) -> dict[str, list[dict]]:
    """各 target_zh -> [{lat,lon,month,sst,sal,chl,front,depth}]，依自己的月份查氣候場(無法查得者丟棄)。"""
    pts: dict[str, list[dict]] = defaultdict(list)
    dropped = 0
    with open(SDM / "occurrences.csv", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            mon = r.get("month") or ""
            if not mon:
                continue
            try:
                lat = float(r["decimalLatitude"])
                lon = float(r["decimalLongitude"])
                m = int(mon)
            except (ValueError, KeyError):
                continue
            if not (1 <= m <= 12):
                continue
            env = snap_env(months, depth_fn, lat, lon, m)
            if env is None:
                dropped += 1
                continue
            pts[r["target_zh"]].append({"lat": lat, "lon": lon, "month": m, **env})
    print(f"  出現點查得氣候場：{sum(len(v) for v in pts.values())}，查不到(丟棄)：{dropped}")
    return pts


def featurize(rows: list[dict]) -> np.ndarray:
    out = np.empty((len(rows), len(FEAT)), dtype=float)
    for k, r in enumerate(rows):
        m = r["month"]
        sst = r["sst"]
        log_chl = math.log(max(r["chl"], CHL_FLOOR))
        log_depth = math.log1p(max(r["depth"], 0.0))
        out[k] = [sst, sst * sst, r["sal"], log_chl, r["front"], log_depth,
                  math.sin(2 * math.pi * m / 12), math.cos(2 * math.pi * m / 12)]
    return out


def fit_logistic(Xs: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    n, p = Xs.shape
    Xa = np.hstack([np.ones((n, 1)), Xs])

    def negll(beta):
        z = Xa @ beta
        ll = np.sum(y * z - np.logaddexp(0.0, z))
        reg = lam * np.sum(beta[1:] ** 2)
        return -ll / n + reg

    def grad(beta):
        pr = 1.0 / (1.0 + np.exp(-(Xa @ beta)))
        g = Xa.T @ (pr - y) / n
        g[1:] += 2 * lam * beta[1:]
        return g

    res = minimize(negll, np.zeros(p + 1), jac=grad, method="L-BFGS-B")
    return res.x


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty(len(allv))
    ranks[order] = np.arange(1, len(allv) + 1)
    r_pos = ranks[: len(pos)].sum()
    u = r_pos - len(pos) * (len(pos) + 1) / 2
    return float(u / (len(pos) * len(neg)))


def boyce_index(p_bg: np.ndarray, p_pres: np.ndarray, bins: int = 10) -> float:
    """簡化版連續 Boyce index：預測值域切 bins 段，presence/background 密度比(P/E)
    對「bin 序」做 Spearman 相關；越接近 1 代表分數越高、出現點越集中(單調可信)。"""
    if len(p_bg) == 0 or len(p_pres) == 0:
        return float("nan")
    lo, hi = float(np.min(p_bg)), float(np.max(p_bg))
    if hi <= lo:
        return float("nan")
    edges = np.linspace(lo, hi, bins + 1)
    ratios: list[tuple[int, float]] = []
    for i in range(bins):
        a, b = edges[i], edges[i + 1]
        in_bg = np.sum((p_bg >= a) & (p_bg < b if i < bins - 1 else p_bg <= b))
        in_pres = np.sum((p_pres >= a) & (p_pres < b if i < bins - 1 else p_pres <= b))
        e = in_bg / len(p_bg)
        if e <= 0:
            continue
        pr = in_pres / len(p_pres)
        if pr > 0:
            ratios.append((i, pr / e))
    if len(ratios) < 3:
        return float("nan")
    idx = np.array([i for i, _ in ratios], dtype=float)
    val = np.array([v for _, v in ratios], dtype=float)
    r_idx = idx.argsort().argsort().astype(float)
    r_val = val.argsort().argsort().astype(float)
    if np.std(r_idx) == 0 or np.std(r_val) == 0:
        return float("nan")
    return float(np.corrcoef(r_idx, r_val)[0, 1])


def block_id(rows: list[dict]) -> list[tuple[int, int]]:
    return [(int(math.floor(r["lat"] / BLOCK_DEG)),
             int(math.floor(r["lon"] / BLOCK_DEG))) for r in rows]


def predict(beta, X_raw, mean, std):
    Xs = (X_raw - mean) / std
    z = beta[0] + Xs @ beta[1:]
    return 1.0 / (1.0 + np.exp(-z))


def spatial_cv(pres_rows, bg_rows) -> tuple[float, float]:
    """空間分塊交叉驗證：回傳 (AUC, Boyce index)。"""
    rows = pres_rows + bg_rows
    y = np.array([1.0] * len(pres_rows) + [0.0] * len(bg_rows))
    X = featurize(rows)
    blocks = block_id(rows)
    fold = np.array([hash(b) % CV_FOLDS for b in blocks])
    aucs, boyces = [], []
    for f in range(CV_FOLDS):
        tr, te = fold != f, fold == f
        if te.sum() == 0 or y[tr].sum() == 0 or (1 - y[tr]).sum() == 0:
            continue
        if y[te].sum() == 0 or (1 - y[te]).sum() == 0:
            continue
        mean = X[tr].mean(axis=0)
        std = X[tr].std(axis=0)
        std[std == 0] = 1.0
        beta = fit_logistic((X[tr] - mean) / std, y[tr], L2)
        p_te = predict(beta, X[te], mean, std)
        aucs.append(auc(p_te[y[te] == 1], p_te[y[te] == 0]))
        boyces.append(boyce_index(p_te[y[te] == 0], p_te[y[te] == 1]))
    a = float(np.nanmean(aucs)) if aucs else float("nan")
    b = float(np.nanmean(boyces)) if boyces else float("nan")
    return a, b


def eastward_check(beta, mean, std, species: str) -> str | None:
    """驗收檢查(issue #10)：該魚種主要季節，預測分數是否偏西——比較東/西部測試點平均分數。
    僅供終端輸出診斷用，不寫入 JSON。"""
    sp = next((s for s in TRAITS if s["name"] == species), None)
    if sp is None or not sp.get("season"):
        return None
    month = sp["season"][len(sp["season"]) // 2]
    west_pts = [(lat, lon) for lat in np.arange(21.5, 25.5, 0.5) for lon in np.arange(119.5, 120.8, 0.3)]
    east_pts = [(lat, lon) for lat in np.arange(21.5, 25.5, 0.5) for lon in np.arange(121.5, 122.8, 0.3)]

    def mean_score(pts):
        rows = []
        for lat, lon in pts:
            env = GLOBAL_ENV_CACHE[0][month].sst(lat, lon)
            if env is None:
                continue
            e = snap_env(GLOBAL_ENV_CACHE[0], GLOBAL_ENV_CACHE[1], lat, lon, month)
            if e is None:
                continue
            rows.append({"month": month, **e})
        if not rows:
            return None
        X = featurize(rows)
        p = predict(beta, X, mean, std)
        return float(np.mean(p))

    w, e = mean_score(west_pts), mean_score(east_pts)
    if w is None or e is None:
        return None
    return f"西部測試點平均分={w:.3f}  東部測試點平均分={e:.3f}  {'東>西(改善)' if e > w else '西>=東(仍偏西)'}"


GLOBAL_ENV_CACHE: list = [None, None]


def build_env_now_grid(months: dict[int, MonthEnv], depth_fn, month: int) -> dict:
    """current 月份氣候場(sal/chl/depth)對齊 fishing_grid.json 的現有格點，供前端推論用。
    sst/front 前端改用即時值現算(見 infer_note)，故這裡不含。"""
    grid = json.loads((SDM / "fishing_grid.json").read_text(encoding="utf-8"))["grid"]
    env = months[month]
    lats, lons, sal, log_chl, log_depth = [], [], [], [], []
    for c in grid:
        if c.get("v") is None:
            continue
        s = env.sal(c["lat"], c["lon"])
        ch = env.chl(c["lat"], c["lon"])
        d = depth_fn(c["lat"], c["lon"])
        if s is None or ch is None or d is None:
            continue
        lats.append(c["lat"])
        lons.append(c["lon"])
        sal.append(round(s, 3))
        log_chl.append(round(math.log(max(ch, CHL_FLOOR)), 4))
        log_depth.append(round(math.log1p(max(d, 0.0)), 4))
    return {"month": month, "lat": lats, "lon": lons,
            "sal": sal, "log_chl": log_chl, "log_depth": log_depth}


def main() -> None:
    months, depth_fn = load_env()
    GLOBAL_ENV_CACHE[0], GLOBAL_ENV_CACHE[1] = months, depth_fn
    pts = load_points(months, depth_fn)
    print(f"occurrence labels: {len(pts)}  total pts: {sum(len(v) for v in pts.values())}")

    all_rows: list[dict] = [r for v in pts.values() for r in v]
    out: dict[str, dict] = {}

    for sp, labels in SPECIES_MAP.items():
        pres = [r for lab in labels for r in pts.get(lab, [])]
        n = len(pres)
        if n < MODEL_MIN:
            out[sp] = {"ok": False, "n": n, "reason": "insufficient"}
            print(f"  [skip] {sp}: n={n} (<{MODEL_MIN})")
            continue
        focal_ids = {id(r) for r in pres}
        bg_pool = [r for r in all_rows if id(r) not in focal_ids]
        n_bg = min(BG_CAP, max(n, min(len(bg_pool), n * BG_PER_PRES)))
        idx = RNG.choice(len(bg_pool), size=n_bg, replace=False)
        bg = [bg_pool[i] for i in idx]

        rows = pres + bg
        y = np.array([1.0] * n + [0.0] * len(bg))
        X = featurize(rows)
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std[std == 0] = 1.0
        beta = fit_logistic((X - mean) / std, y, L2)
        p_app = predict(beta, X, mean, std)
        auc_app = auc(p_app[y == 1], p_app[y == 0])
        auc_cv, boyce = spatial_cv(pres, bg)

        out[sp] = {
            "ok": True,
            "coef": [round(float(b), 5) for b in beta],
            "mean": [round(float(m), 5) for m in mean],
            "std": [round(float(s), 5) for s in std],
            "auc": round(auc_cv, 3) if not math.isnan(auc_cv) else None,
            "auc_app": round(auc_app, 3),
            "boyce": round(boyce, 3) if not math.isnan(boyce) else None,
            "n": n,
        }
        diag = eastward_check(beta, mean, std, sp)
        print(f"  [model] {sp}: n={n} bg={len(bg)} AUC_cv={auc_cv:.3f} Boyce={boyce:.3f} AUC_app={auc_app:.3f}")
        if diag:
            print(f"           {diag}")

    import datetime as dt
    cur_month = dt.date.today().month
    env_now = build_env_now_grid(months, depth_fn, cur_month)
    print(f"env_now(月={cur_month})：{len(env_now['lat'])} 格(對齊 fishing_grid)")

    payload = {
        "feat": FEAT,
        "infer_note": "推論時 sst_clim 由前端即時 SST 現算取代(更準)，sal_clim/log_chl/log_depth 用 env_now 氣候場",
        "species": out,
        "env_now": env_now,
    }
    (SDM / "sdm_now.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    modeled = sum(1 for v in out.values() if v.get("ok"))
    print(f"done: modeled {modeled}/{len(SPECIES_MAP)} species -> sdm/sdm_now.json")


if __name__ == "__main__":
    main()
