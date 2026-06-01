# NODASS 海洋大數據儀表板 — 專案脈絡（給 AI agent 與協作者）

> 2026 第四屆諾大師海洋大數據競賽作品。本檔由 Claude Code 自動載入，目的是讓任何接手的
> AI agent 與同學「零資料/思維斷層」繼續開發。先讀本檔再動手。

## 一句話
用台灣政府公開海洋資料，做「漁場棲地（過去·現在·未來）」與「極端浪況預警」儀表板，
作為漁民出航前的**決策參考平台**（非漁獲保證、非官方海象警報）。

## 快速開始
- 看成果：直接開 `dashboard/platform.html`（自含式，免後端）。線上：https://yee645.github.io/nodass-ocean-dashboard/
- 依賴：`pip install -r requirements.txt`（numpy / scipy / Pillow / PyMuPDF）。網路請求用標準庫 urllib。
- 一鍵重建（開放資料）：`bash setup.sh`（或 `pwsh setup.ps1`）。
- 平台 = `dashboard/platform.html`，以 iframe 整合三個棲地子頁 + 極端浪況頁。

## 資料存取地圖（最關鍵的「思維」，先懂這個）
| 來源 | 用途 | 存取 | 範圍/時間 |
|---|---|---|---|
| NODASS 開放浮標 API | 即時海溫/波浪/海流 | 免 token | 近 2 日、26 站 |
| NODASS 開放衛星影像 API | Sentinel-3 海溫 `SLNT_S3_SST`、GOCI 葉綠素 `GOCI_CHL` | **免 token** | archive 約 2019–2021，彩色 JPEG（需數位化） |
| **CWA OCM OPeNDAP** | 數值預報 SST/海流(UCURR,VCURR)/鹽度/風(WS,WD)/水位(WL) | **公開、免授權** | 未來 120 小時(5天)、0.025°、~1 天延遲 |
| TFRIN 漁場環境 | 溫鹽/葉綠素站點(PDF 表格) | 公開 | 2004–2014，`tfrin.gov.tw/ws.php?id=70` |
| TaiBIF / GBIF | 魚種出現點(SDM 標籤) | 公開檔(已下載於 `data/`，gitignore) | 1945–2026 |
| NODASS **管制**資料 | 數值預報模式 `CWB_OCM`(48)/`HYCOM`(54)/`NAMR_POM`(115) | **403，需申請會員管制權限** | 未用——已用 CWA OCM 開放源替代 |

- 端點樣式：`https://nodass.namr.gov.tw/noapi/namr/v1/images/{ClassCode}?date1=&date2=`；
  `https://oceanapi.cwa.gov.tw/opendap/OCM/{YYYYMMDD}/00/9999/{VAR}.{YYYYMMDD}00.nc`（OPeNDAP ascii 約束式需 URL 編碼 `%5B%3A%5D`）。
- `.nodass_token` 為機密（gitignore，勿外流）；目前所有管線都用開放源，不需它。

## 架構與檔案
- **入口**：`dashboard/platform.html`（時段切換：過去衛星 / 現在浮標 / 未來 CWA，iframe 載入子頁）。
- **頁面與產生器**：
  - `build_dashboard.py` → `dashboard/index.html`：極端浪況預警（浮標波高風險 + 時間軸）。
  - `build_fishing.py` → `dashboard/fishing.html`：即時浮標漁場棲地、魚群熱區/漂移、時間軸。
  - `build_hires.py` → `dashboard/hires.html`：衛星 ~4km 棲地 + 資料驅動 SDM（空間 CV AUC）。
  - `build_forecast.py` → `dashboard/forecast.html`：CWA OCM 未來數日棲地 + 葉綠素氣候場 + 海流。
  - `build_platform.py` → `dashboard/platform.html`：整合入口。
- **共用**：`dashboard_common.py`（SHARED_CSS、nav_html、海岸線遮罩 on_land、IDW、海岸線）。
- **資料管線**：`fetch_buoys.py`、`fetch_satellite.py`+`sat_digitize.py`（衛星數位化）、`fetch_ocm_forecast.py`（CWA OCM）、`fetch_tfrin_env.py`（TFRIN PDF）、`build_occurrences.py`（整併物種出現點）、`build_sdm.py`（presence-only 高斯包絡 SDM）。
- **魚種習性**：`species_traits.py`（10 種經濟魚種適溫窗、季節、習性）。
- `live_update.py`：fetch_buoys → accumulate_history → build_dashboard → build_fishing。
- `make_region_coast.py`：由 Natural Earth 產生 `region_coast.json`（含中國大陸沿海，供陸地遮罩/底圖）。

## 執行順序（重建）
1. `python fetch_buoys.py`（即時浮標）→ `build_dashboard.py`、`build_fishing.py`
2. `python build_hires.py`（自動抓開放衛星，需網路）
3. `python build_forecast.py`（自動抓 CWA OCM + GOCI，需網路）
4. `python build_platform.py`
5.（選用）`build_occurrences.py` 需 `data/` 原始生物資料；其輸出 `sdm/occurrences.csv` 已上傳，故 `build_sdm.py`/`build_hires.py` 不需原始資料即可跑。

## 誠實準確度（寫報告與對使用者溝通時務必照實）
- 高解析 SDM：**空間分塊交叉驗證 AUC 0.75–0.90**（17 種，與隨機 CV 接近，非空間自相關假象）。
- 這是「棲地適合度/出現潛勢」，**不是漁獲量**；目前**無 CPUE 標籤**，無法預測魚量。
- 衛星 archive 止於約 2021；「今日/未來」高解析靠 CWA OCM 數值預報；葉綠素預報用氣候平均。
- 定位：海象與環境可作**參考**（安全以中央氣象署海象/漁業氣象、海巡警報為準）；魚群為**潛勢非保證**。

## 待辦（路線圖）
- **P1（已完成）**：三棲地頁整合為 `platform.html`（iframe 時段切換）。
  - P1.5（可再做）：改為單一地圖共享魚種勾選狀態的深度整合（目前各子頁各自渲染）。
- **P2**：補「未來海象」安全層——OCM 風/流/潮 + CWA 波浪預報（CWA 開放資料 API 免費金鑰，或 NODASS 管制）。
- **P3**：加 Global Fishing Watch 船隊作業熱區（AIS，需免費金鑰）+ 各區/魚種「信心圖層」。
- **P4（質變，需資料）**：取得漁業署漁獲/VMS/CPUE → 把棲地升級為驗證過的漁獲潛勢/CPUE 預測。

## gitignored 資料（clone 後會缺，及**下載連結/重抓方式**）
- `data/gbif_taiwan_fish.csv`（魚種出現點）：
  - **可重現重抓（推薦，免金鑰）**：`python fetch_occurrences.py` → 由 GBIF API 重建。
  - GBIF API：`https://api.gbif.org/v1/occurrence/search`（taxonKey + geometry WKT 框 + hasCoordinate）。
  - GBIF 入口（人工檢視/匯出）：https://www.gbif.org/occurrence/search?geometry=POLYGON((118%2020,124%2020,124%2027,118%2027,118%2020))&has_coordinate=true
- `data/全球生物多樣性資料庫(TaiBIF)生物調查資料/`、`臺灣底拖與深海採集資料/`（DwCA）：
  - 來源：TaiBIF IPT https://ipt.taibif.tw 、GBIF 資料集搜尋 https://www.gbif.org/dataset/search（底拖=bottom_trawl、深海=deep-sea-fishes）。
  - 註：**僅 `build_occurrences.py` 需要這些原始檔**；其輸出 `sdm/occurrences.csv` 已隨庫提供，下游 `build_sdm`/`build_hires` 不需原始資料。
- `_sat_cache/`、`_tfrin_pdf/`：由 `fetch_satellite.py`/`fetch_tfrin_env.py` 自動重抓（開放、免金鑰）。
- `.nodass_token`：機密，勿外流；目前所有管線都用開放源，不需它。

## 專案慣例（沿用 owner 的全域規則；協作 agent 請遵守）
- 全部輸出用**繁體中文**（台灣慣用語），**不用 emoji**。
- **未經明確要求，勿新增 `.md` 檔**（本檔與 README 已獲同意）。
- 統計圖表內文字用**英文**；程式註解/說明用繁中。
- 路徑盡量相對；非經要求勿產生測試碼（若有，置於 `tests/`）。
- commit 訊息用 conventional commits（feat/fix/refactor/ui/docs…）。
