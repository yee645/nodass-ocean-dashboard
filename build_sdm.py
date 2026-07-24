"""第一版物種分布模型(SDM)：用 TFRIN 海域環境資料內插成環境網格，
對出現點充足的經濟魚種建立 presence-only 高斯/馬氏距離棲地包絡模型。

輸入：
  sdm/tfrin_env.csv   ：水試所溫鹽(TS)/葉綠素(CHL)站點資料（fetch_tfrin_env.py 產出）。
  sdm/occurrences.csv ：魚種出現點（build_occurrences.py 產出）。
環境協變數（皆由 TFRIN 站點 IDW 內插至 0.05° 海域網格，全程 TFRIN/水試所資料）：
  sst        ：表層(<=10m)海溫 (°C)
  sal        ：表層(<=10m)鹽度 (psu)
  chl        ：葉綠素總量 (>10μm + <10μm, mg/m3)
  bdepth     ：測站底深 (m，地形代理)
模型：以出現點環境分布擬合多維高斯，棲地適合度 = exp(-0.5 * Mahalanobis^2)，標準化 0–100。
輸出：sdm/sdm_grid.json（各魚種網格適合度）、sdm/sdm_report.csv（筆數與 AUC）。

註：第一版為 presence-only 包絡法（BIOCLIM/ENFA 族），透明可解釋；曾實測換成判別式模型
    （QDA/多項式邏輯迴歸，見 train_sdm_model.py）不會更準——樣本量(20–71 筆)撐不起判別式模型的
    leave-one-block-out 空間 CV，包絡模型對小樣本更穩健，見 CLAUDE.md「誠實準確度」。
    可考慮以多航次氣候平均環境場取代單一航次快照。
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from dashboard_common import haversine, on_land

BASE = Path(__file__).resolve().parent
SDM = BASE / "sdm"
GRID_STEP = 0.05
LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = 117.0, 123.0, 20.0, 27.0
ENV_RADIUS_KM = 90.0          # 環境內插半徑（站距約 55km）
MIN_PRESENCE = 15             # 建模所需最少（落在環境涵蓋內的）出現點
COVARS = ["sst", "sal", "chl", "bdepth"]


def load_env() -> dict[str, list[tuple[float, float, float]]]:
    """回傳各協變數的 (lat, lon, value) 點集。"""
    pts: dict[str, list] = {k: [] for k in COVARS}
    with open(SDM / "tfrin_env.csv", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            lat, lon = float(r["lat"]), float(r["lon"])
            depth = r.get("depth_m") or ""
            if r["kind"] == "TS":
                d = float(depth) if depth else 99
                if d <= 10:                       # 表層
                    if r["temperature_c"]:
                        pts["sst"].append((lat, lon, float(r["temperature_c"])))
                    if r["salinity_psu"]:
                        pts["sal"].append((lat, lon, float(r["salinity_psu"])))
            else:                                  # CHL：depth_m 為測站底深
                tot = 0.0
                for c in ("chl_gt10", "chl_lt10"):
                    if r.get(c):
                        tot += float(r[c])
                if r.get("chl_gt10") or r.get("chl_lt10"):
                    pts["chl"].append((lat, lon, tot))
                if depth:
                    pts["bdepth"].append((lat, lon, float(depth)))
    return pts


def idw(points, lat, lon, radius=ENV_RADIUS_KM):
    num = den = 0.0
    nearest = 1e9
    for plat, plon, pval in points:
        d = haversine(lat, lon, plat, plon)
        nearest = min(nearest, d)
        if d <= radius:
            w = 1.0 / (d * d + 1.0)
            num += w * pval
            den += w
    return num / den if (den > 0 and nearest <= radius) else None


def build_env_grid(pts) -> list[dict]:
    """內插出含完整 4 協變數的海域網格。"""
    grid = []
    lat = LAT_MIN
    while lat <= LAT_MAX:
        lon = LON_MIN
        while lon <= LON_MAX:
            if not on_land(lon, lat):
                cell = {"lat": round(lat, 3), "lon": round(lon, 3)}
                ok = True
                for k in COVARS:
                    v = idw(pts[k], lat, lon)
                    if v is None:
                        ok = False
                        break
                    cell[k] = v
                if ok:
                    grid.append(cell)
            lon += GRID_STEP
        lat += GRID_STEP
    return grid


def load_occurrences() -> dict[str, list[tuple[float, float]]]:
    occ = defaultdict(list)
    with open(SDM / "occurrences.csv", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            occ[r["target_zh"]].append((float(r["decimalLatitude"]),
                                        float(r["decimalLongitude"])))
    return occ


def nearest_cell(grid, lat, lon, tol=GRID_STEP * 1.5):
    best, bd = None, 1e9
    for c in grid:
        d = abs(c["lat"] - lat) + abs(c["lon"] - lon)
        if d < bd:
            bd, best = d, c
    return best if (best and bd <= tol * 2) else None


def auc(pres_scores, bg_scores) -> float:
    """Mann–Whitney U 推導 AUC：隨機背景點被排在出現點之下的機率。"""
    pres = np.asarray(pres_scores)
    bg = np.asarray(bg_scores)
    if len(pres) == 0 or len(bg) == 0:
        return float("nan")
    allv = np.concatenate([pres, bg])
    order = allv.argsort()
    ranks = np.empty(len(allv))
    ranks[order] = np.arange(1, len(allv) + 1)
    r_pres = ranks[:len(pres)].sum()
    u = r_pres - len(pres) * (len(pres) + 1) / 2
    return round(float(u / (len(pres) * len(bg))), 3)


def main() -> None:
    pts = load_env()
    print("env points:", {k: len(v) for k, v in pts.items()})
    grid = build_env_grid(pts)
    print(f"env grid cells (full covariates): {len(grid)}")
    if not grid:
        print("環境網格為空，無法建模（環境資料涵蓋不足）。")
        return

    X = np.array([[c[k] for k in COVARS] for c in grid], dtype=float)
    mu_all = X.mean(axis=0)
    sd_all = X.std(axis=0)
    sd_all[sd_all == 0] = 1.0
    Xs = (X - mu_all) / sd_all                       # 全網格標準化

    occ = load_occurrences()
    species = sorted(occ, key=lambda s: len(occ[s]), reverse=True)

    results = {}        # sp -> list[suit per grid cell]
    report = []
    for sp in species:
        # 出現點對應到網格協變數
        rows = []
        for lat, lon in occ[sp]:
            c = nearest_cell(grid, lat, lon)
            if c:
                rows.append([c[k] for k in COVARS])
        if len(rows) < MIN_PRESENCE:
            report.append((sp, len(occ[sp]), len(rows), "skip-不足"))
            continue
        P = (np.array(rows, dtype=float) - mu_all) / sd_all
        mu = P.mean(axis=0)
        cov = np.cov(P, rowvar=False) + np.eye(len(COVARS)) * 1e-3
        cov_inv = np.linalg.inv(cov)
        diff = Xs - mu
        d2 = np.einsum("ij,jk,ik->i", diff, cov_inv, diff)
        suit = np.exp(-0.5 * d2)
        suit = suit / suit.max() * 100.0
        results[sp] = [round(float(v), 1) for v in suit]
        # AUC：出現點所在網格 vs 全網格背景
        pres_cell_scores = []
        for lat, lon in occ[sp]:
            c = nearest_cell(grid, lat, lon)
            if c:
                pres_cell_scores.append(suit[grid.index(c)])
        a = auc(pres_cell_scores, suit)
        report.append((sp, len(occ[sp]), len(rows), a))
        # 主控台只輸出 ASCII（避免 Windows cp950 編碼錯誤）；魚種名在 CSV
        print(f"  species#{len(results)}: presence={len(rows)} AUC={a}")

    # 輸出網格適合度
    out_cells = []
    for i, c in enumerate(grid):
        cell = {"lat": c["lat"], "lon": c["lon"],
                "sst": round(c["sst"], 2), "chl": round(c["chl"], 3),
                "s": {sp: results[sp][i] for sp in results}}
        out_cells.append(cell)
    (SDM / "sdm_grid.json").write_text(
        json.dumps({"step": GRID_STEP, "species": list(results),
                    "cells": out_cells}, ensure_ascii=False,
                   separators=(",", ":")), encoding="utf-8")

    with open(SDM / "sdm_report.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["魚種", "出現點總數", "建模可用點數", "AUC/狀態"])
        for row in report:
            w.writerow(row)

    modeled = len(results)
    print(f"done: modeled species={modeled}  grid cells={len(grid)} "
          f"-> sdm/sdm_grid.json, sdm/sdm_report.csv")


if __name__ == "__main__":
    main()
