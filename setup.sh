#!/usr/bin/env bash
# 一鍵重建（開放資料，免授權）。需網路：會抓即時浮標、開放衛星影像、CWA OCM 預報。
set -e
cd "$(dirname "$0")"
echo "[1/6] 安裝依賴"; pip install -r requirements.txt
echo "[2/6] 抓即時浮標";          python fetch_buoys.py
echo "[3/6] 極端浪況頁";          python build_dashboard.py
echo "[4/6] 即時漁場頁";          python build_fishing.py
echo "[5/6] 高解析衛星 + 未來預報"; python build_hires.py && python build_forecast.py
echo "[6/6] 整合平台";            python build_platform.py
echo "完成。請開啟 dashboard/platform.html"
# 註：重新產生魚種出現點(build_occurrences.py)需 data/ 原始生物資料(見 CLAUDE.md)；
#     其輸出 sdm/occurrences.csv 已隨庫提供，故下游 build_sdm/build_hires 無需原始資料。
