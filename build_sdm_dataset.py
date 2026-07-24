"""從既有 sdm/hires_grid.json（已算好的 sst/chl/front 網格）+ occurrences.csv
統整出訓練資料集 sdm/sdm_training_dataset.csv，供之後訓練 sklearn 模型比較用。

跟 build_hires.py 的 fit_hires_sdm() 走同一套特徵/背景抽樣/空間分塊邏輯，
差別只是特徵直接讀現成的 hires_grid.json，不必重新呼叫衛星 API——
繞開目前 NODASS/CWA 主機共通的 Python SSL 憑證問題（見 TODO.md），
之後 SSL 問題解決、`python build_hires.py` 重新跑過一次後，
其內建的匯出（同樣寫到這個檔案）會用當次新鮮抓的衛星資料覆蓋掉這份，屬正常汰換。

輸出欄位：species,label(1=出現/0=背景),sst_z,chl_log_z,front_z,lat,lon,block(空間分塊 CV 用)。
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
GRID_JSON = BASE / "sdm" / "hires_grid.json"
OCC_CSV = BASE / "sdm" / "occurrences.csv"
OUT_CSV = BASE / "sdm" / "sdm_training_dataset.csv"

MIN_PRESENCE_SDM = 20  # 與 build_hires.py 一致
BS = 0.6               # 空間分塊邊長(度)，與 build_hires.py 的空間分塊 CV 一致
N_BG = 2000


def main() -> None:
    if not GRID_JSON.exists():
        print(f"找不到 {GRID_JSON}，請先跑過一次 python build_hires.py 產生它。")
        return

    payload = json.loads(GRID_JSON.read_text(encoding="utf-8"))
    lat = payload["lat"]
    lon = payload["lon"]
    sst = payload["layers"]["sst"]
    chl = payload["layers"]["chl"]
    front = payload["layers"]["front"]
    west, north = payload["meta"]["bbox"][0], payload["meta"]["bbox"][3]
    step = payload["meta"]["step"]

    valid = [i for i in range(len(lat))
             if sst[i] is not None and chl[i] is not None and chl[i] > 0 and front[i] is not None]
    print(f"grid cells total={len(lat)}  valid(sst+chl+front)={len(valid)}")

    chl_log = {i: np.log10(chl[i]) for i in valid}
    feats = {i: (sst[i], chl_log[i], front[i]) for i in valid}
    arr = np.array([feats[i] for i in valid])
    mu, sd = arr.mean(axis=0), arr.std(axis=0)
    sd[sd == 0] = 1.0
    Zs = {i: ((np.array(feats[i]) - mu) / sd) for i in valid}

    cell_lookup = {(round(lat[i], 3), round(lon[i], 3)): i for i in valid}

    def snap(la: float, lo: float) -> int | None:
        iy = round((north - la) / step)
        ix = round((lo - west) / step)
        key = (round(north - iy * step, 3), round(west + ix * step, 3))
        return cell_lookup.get(key)

    occ = defaultdict(set)
    with open(OCC_CSV, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            idx = snap(float(r["decimalLatitude"]), float(r["decimalLongitude"]))
            if idx is not None:
                occ[r["target_zh"]].add(idx)

    rng = np.random.default_rng(42)
    bg = rng.choice(valid, min(N_BG, len(valid)), replace=False).tolist()

    def block_of(i: int) -> str:
        return f"{int(lat[i] // BS)}_{int(lon[i] // BS)}"

    rows = []
    n_species = 0
    for sp, cells in sorted(occ.items(), key=lambda kv: len(kv[1]), reverse=True):
        if len(cells) < MIN_PRESENCE_SDM:
            continue
        n_species += 1
        for i in cells:
            z = Zs[i]
            rows.append((sp, 1, *z.tolist(), lat[i], lon[i], block_of(i)))
        for i in bg:
            z = Zs[i]
            rows.append((sp, 0, *z.tolist(), lat[i], lon[i], block_of(i)))

    OUT_CSV.parent.mkdir(exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["species", "label", "sst_z", "chl_log_z", "front_z", "lat", "lon", "block"])
        w.writerows(rows)
    n_pres = sum(1 for r in rows if r[1] == 1)
    print(f"species modeled={n_species}  rows={len(rows)} ({n_pres} presence / {len(rows) - n_pres} background)"
          f"  -> {OUT_CSV}")


if __name__ == "__main__":
    main()
