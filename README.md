# NODASS 海洋大數據儀表板

2026 第四屆諾大師海洋大數據競賽作品。以台灣政府**公開**海洋資料，打造「**漁場棲地（過去·現在·未來）**」與「**極端浪況預警**」儀表板，作為漁民出航前的決策**參考平台**。

線上展示：https://yee645.github.io/nodass-ocean-dashboard/

> 協作的 AI agent 請先讀 [`CLAUDE.md`](CLAUDE.md)（含資料來源、架構、誠實準確度、路線圖），可零斷層接手。

## 功能
- **漁場棲地平台**（`dashboard/platform.html`）：單一入口，切換
  - 過去 · 高解析衛星（~4km 海溫/葉綠素/鋒面 + 資料驅動 SDM，空間交叉驗證 AUC 0.75–0.90）
  - 現在 · 即時浮標（海溫與魚種棲地、魚群熱區與漂移、近兩日時間軸）
  - 未來 · CWA 預報（氣象署 OCM 未來數日海溫/海流 + 葉綠素，多魚種棲地）
- **極端浪況預警**（`dashboard/index.html`）：全台浮標波高風險與時間軸回放。
- 多魚種勾選、最適魚種合成、點圖查經緯度與海況。

## 安裝與重建
```bash
pip install -r requirements.txt
bash setup.sh        # 或 Windows: pwsh setup.ps1
# 完成後開啟 dashboard/platform.html
```
各頁也可單獨重建：`python build_fishing.py` / `build_hires.py` / `build_forecast.py` / `build_platform.py`（hires、forecast 會自動抓開放衛星與 CWA OCM，需網路）。

## 資料來源（使用須註明）
- 國家海洋資料庫及共享平臺（NODASS）開放浮標與衛星影像 API
- 中央氣象署（CWA）OCM 海流模式（oceanapi OPeNDAP）
- 水產試驗所（TFRIN）臺灣周邊海域漁場環境資料
- TaiBIF / GBIF 物種出現紀錄、Natural Earth 海岸線

## 準確度與免責
- 魚群圖層為「**環境棲地潛勢**」（presence-only SDM，空間 CV AUC 0.75–0.90），**非漁獲量保證**。
- 出海安全請以**中央氣象署海象/漁業氣象預報與海巡警報為準**；本平台僅供參考。

## 授權與貢獻
- 直接 clone 即可瀏覽與開發；要共同推送請聯絡 repo 擁有者加為協作者，或 fork 後發 PR。
- 路線圖與待辦見 `CLAUDE.md`（P2 海象安全層 / P3 船隊熱區與信心圖 / P4 漁獲 CPUE）。
