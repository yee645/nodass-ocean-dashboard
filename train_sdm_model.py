"""拿 sdm/sdm_training_dataset.csv 訓練 sklearn 模型，跟現行高斯包絡模型
（build_hires.py 的 fit_hires_sdm()，報表見 sdm/hires_sdm_report.csv）比較空間分塊 CV AUC。

驗證方式跟現行模型同一套「leave-one-block-out」(0.6°方塊)，才是公平比較：
訓練/測試切分完全依 sdm_training_dataset.csv 裡已經算好的 block 欄位，不重新分。

背景點(label=0)當作 pseudo-absence，presence:background 比例懸殊(約 1:51)，
兩個分類器都開 class_weight='balanced' 處理不平衡，不做過採樣/欠採樣（樣本數對這個資料量夠用，
不需要額外複雜度）。

模型選擇說明：先試過 plain LogisticRegression，AUC 只有 0.49–0.61，比包絡模型差一截
（連 in-sample/不做 CV 都才 0.68）。原因不是 bug，是特徵空間結構：presence-only 的環境利基
在 (sst, log 葉綠素, 鋒面) 這 3 維空間裡是「有界的一團」，線性分類器天生只能切一刀(超平面)，
包不住一團有界分布——這正是原本選 Mahalanobis 距離包絡模型的道理。改用能表達彎曲邊界的模型
（QDA=判別分析版的高斯包絡、多項式特徵邏輯迴歸）才是公平比較。

輸出：sdm/sdm_model_comparison.csv（魚種, 出現點數, 包絡模型AUC, QDA-AUC, 多項式邏輯迴歸AUC）。
本檔只做比較評估，不覆寫任何現行產物；確認有提升後再決定要不要真的換掉 fit_hires_sdm()。
"""
from __future__ import annotations

import csv
import io
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = Path(__file__).resolve().parent
DATASET = BASE / "sdm" / "sdm_training_dataset.csv"
REPORT = BASE / "sdm" / "hires_sdm_report.csv"
OUT = BASE / "sdm" / "sdm_model_comparison.csv"

FEATURES = ["sst_z", "chl_log_z", "front_z"]


def load_envelope_baseline() -> dict[str, float]:
    baseline = {}
    with open(REPORT, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            sp = r.get("﻿魚種") or r.get("魚種")
            scv = r.get("空間分塊CV-AUC")
            if scv and scv not in ("", "nan"):
                try:
                    baseline[sp] = float(scv)
                except ValueError:
                    pass
    return baseline


def make_qda():
    return QuadraticDiscriminantAnalysis(reg_param=0.3)


def make_poly_logreg():
    return make_pipeline(
        PolynomialFeatures(degree=2, include_bias=False),
        LogisticRegression(class_weight="balanced", max_iter=2000),
    )


def spatial_cv_auc(make_model, X, y, blocks) -> float:
    """leave-one-block-out：每次留一個空間分塊當測試集，其餘訓練。"""
    uniq = sorted(set(blocks))
    aucs = []
    for hold in uniq:
        te = [i for i, b in enumerate(blocks) if b == hold]
        tr = [i for i, b in enumerate(blocks) if b != hold]
        y_te = [y[i] for i in te]
        # 測試集要同時有正負樣本才能算 AUC；block 內全是背景點(label=0)很常見，跳過
        if len(set(y_te)) < 2 or sum(y[i] for i in tr) < 3:
            continue
        model = make_model()
        model.fit([X[i] for i in tr], [y[i] for i in tr])
        proba = model.predict_proba([X[i] for i in te])[:, 1]
        aucs.append(roc_auc_score(y_te, proba))
    return round(float(np.mean(aucs)), 3) if aucs else float("nan")


def main() -> None:
    if not DATASET.exists():
        print(f"找不到 {DATASET}，請先跑 python build_sdm_dataset.py。")
        return

    by_species: dict[str, list[dict]] = defaultdict(list)
    with open(DATASET, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            by_species[r["species"]].append(r)

    baseline = load_envelope_baseline()
    rows = []
    for sp, recs in sorted(by_species.items(), key=lambda kv: -len(kv[1])):
        X = [[float(r[f]) for f in FEATURES] for r in recs]
        y = [int(r["label"]) for r in recs]
        blocks = [r["block"] for r in recs]
        n_pres = sum(y)

        auc_qda = spatial_cv_auc(make_qda, X, y, blocks)
        auc_poly = spatial_cv_auc(make_poly_logreg, X, y, blocks)
        env_auc = baseline.get(sp, float("nan"))
        rows.append((sp, n_pres, env_auc, auc_qda, auc_poly))
        print(f"  {sp}: n={n_pres} envelope={env_auc} qda={auc_qda} poly_logreg={auc_poly}")

    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["魚種", "出現點數", "包絡模型AUC(現行)", "QDA-AUC", "多項式邏輯迴歸AUC"])
        w.writerows(rows)

    valid = [r for r in rows if r[2] == r[2]]  # 排除 NaN
    if valid:
        print(f"\n平均：envelope={np.mean([r[2] for r in valid]):.3f} "
              f"qda={np.mean([r[3] for r in valid]):.3f} "
              f"poly_logreg={np.mean([r[4] for r in valid]):.3f}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
