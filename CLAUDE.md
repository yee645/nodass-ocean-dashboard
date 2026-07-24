# NODASS 海洋大數據儀表板 — 專案脈絡（給 AI agent 與協作者）

> 2026 第四屆諾大師海洋大數據競賽作品。本檔由 Claude Code 自動載入，目的是讓任何接手的
> AI agent 與同學「零資料/思維斷層」繼續開發。先讀本檔再動手。

## 一句話
用台灣政府公開海洋資料，做「漁場棲地（過去·現在·未來）」與「極端浪況預警」儀表板，
作為漁民出航前的**決策參考平台**（非漁獲保證、非官方海象警報）。

## 快速開始
- 看成果（目前線上部署版，穩定）：直接開 `dashboard/platform.html`（自含式，免後端）。線上：https://yee645.github.io/nodass-ocean-dashboard/
- 依賴：`pip install -r requirements.txt`（numpy / scipy / Pillow / PyMuPDF）。網路請求用標準庫 urllib。
- 一鍵重建（開放資料）：`bash setup.sh`（或 `pwsh setup.ps1`）。
- 平台 = `dashboard/platform.html`，以 iframe 整合三個棲地子頁 + 極端浪況頁。
- `web/` 為進行中的 React SPA 重構（見下方專節），**尚未部署**，`dashboard/*.html` 仍是現行對外版本，開發時勿誤刪。

## 開發指令
- Python 管線：無 lint/test 設定；各頁重建指令見下方「執行順序」。
- React 前端（`web/`）：
  - `cd web && npm install`（首次）
  - `npm run dev`：本機開發伺服器（Vite，含 HMR）
  - `npm run build`：`tsc -b && vite build`，型別檢查 + 產出 `web/dist`
  - `npm run lint`：ESLint（flat config，`typescript-eslint` + `react-hooks` + `react-refresh`）
  - `npm run preview`：預覽 production build
  - 無測試指令/測試檔（目前無自動化測試）。

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
- **航線規劃（第二層）資料**：`build_ports.py`（漁港起點 `sdm/ports.json`）、`build_bathymetry.py`（純 Python 讀 GEBCO GeoTIFF(`nodass.tif`，需人工從 download.gebco.net 下載一次)，用 tifffile 讀像素陣列＋numpy 分級＋skimage 的 `find_contours`(取代 QGIS polygonize+dissolve)/`approximate_polygon`(取代 QGIS simplify) 產生等深帶多邊形 `sdm/depth_bands.json`；不需 QGIS/GDAL——這一步是離線一次性資料前處理，非即時後端，不影響本專案純靜態前端架構）、`fetch_conservation_zones.py`（漁業資源保育區文字座標解析 `sdm/restricted_zones.json`，含人工抽查機制）、`fetch_tide.py`（潮汐測站目前潮位 `sdm/tide.json`，scaffold，需 `.cwa_token`，供水深門檻做單點潮位修正，非全網格逐時模擬）。
- **魚種習性**：`species_traits.py`（10 種經濟魚種適溫窗、季節、習性）。
- `live_update.py`：fetch_buoys → accumulate_history → build_dashboard → build_fishing。
- `make_region_coast.py`：由 Natural Earth 產生 `region_coast.json`（含中國大陸沿海，供陸地遮罩/底圖）。

## 執行順序（重建）
1. `python fetch_buoys.py`（即時浮標）→ `build_dashboard.py`、`build_fishing.py`
2. `python build_hires.py`（自動抓開放衛星，需網路）
3. `python build_forecast.py`（自動抓 CWA OCM + GOCI，需網路）
4. `python build_platform.py`
5.（選用）`build_occurrences.py` 需 `data/` 原始生物資料；其輸出 `sdm/occurrences.csv` 已上傳，故 `build_sdm.py`/`build_hires.py` 不需原始資料即可跑。
6.（開發 `web/` 時）`python sync_web_data.py`：把 `sdm/forecast_grid.json`、`sdm/hires_grid.json`、`sdm/fishing_grid.json`、`region_coast.json`、`sdm/ports.json`、`sdm/occurrences_web.json`、`sdm/depth_bands.json`、`sdm/restricted_zones.json`、`sdm/tide.json` 複製到 `web/public/data/`，React 端才吃得到新資料。尚未併入 `setup.sh`，Python 產物更新後需手動執行。

## React 前端（`web/`）— 重構進行中，尚未部署
> 目標：功能/API 與現有 `dashboard/*.html` **1:1 一致**，只做美化與加速；科學計算仍在 Python，TS 端不重算。

- **技術棧**：Vite + React 19 + TypeScript + Tailwind v4 + Zustand（狀態）+ TanStack Query（資料 fetch）+ Chart.js(`react-chartjs-2`)。
- **地圖引擎**：MapLibre GL（底圖）+ deck.gl `MapboxOverlay`（所有資料圖層，WebGL），取代舊版 Leaflet。
- **頁面拓樸**：單一 SPA、共用一張地圖（取消舊版 iframe + postMessage）。三時段（過去/現在/未來）切換不重載地圖，魚種選擇跨時段共享於 Zustand。
- **資料流**：Python `build_*.py` 只負責產出靜態 JSON（`sdm/*.json`）→ `sync_web_data.py` 複製到 `web/public/data/` → React `useData.ts`（TanStack Query）fetch 消費。JSON schema 的權威定義在 `web/src/data/contracts.ts`（對齊 `build_forecast.py`/`build_fishing.py`/`build_hires.py` 輸出），改動 Python 輸出欄位時務必同步更新此檔。
- **狀態核心**：`web/src/store/useAppStore.ts`（Zustand）—— `timeMode`(past/now/future)、互斥的 `baseField`(純量場單選)、可複選的 `overlays`(海流/風向量/出現點/浮標)、跨時段共享的 `species`。`modes/modeConfig.ts` 存三時段中繼資料（對應舊 `platform.html` 的 `MODES`）。
- **圖層堆疊**：`map/layerOrder.ts` 的 `LAYER_ORDER` 陣列即權威 z-order（取代 Leaflet pane），圖層 id 需以此陣列項目為前綴（例 `gridField-sst`）。區分「互斥 base（純量場單選）」vs「可混用 overlay（向量/出現點/浮標複選）」；低信心淡化是修飾子（`confDim`），非獨立圖層。
- **關鍵目錄**：`web/src/map/layers/`（各圖層建構，如 `hotspotLayers.ts`/`hotspotModel.ts` 為魚群熱區連通分群+漂移、`hiresMath.ts`/`nowMath.ts` 為 TS 端純函式數值處理、`routeLayer.ts` 畫航線）；`web/src/components/`（`LeftPanel`/`LayerPanel`/`TimeBar` 等殼層 UI，`now/` 子目錄為現在時段的時序圖/站點表/航線規劃面板）。
- **航線規劃（第二層，僅「現在」時段）**：`map/route/costGrid.ts`（`fish`/`short`/`safe`/`fuel` 四種目標成本場）+ `astar.ts`（0.05° 網格 8 鄰接 A*，純函式）+ `routeCells.ts`（把 `fishing_grid` 併入水深/保育區/陸地限制組成 `RouteCell[]`）+ `components/now/RoutePanel.tsx`（起訖點/目標/吃水/續航 UI）。起點可選漁港（`sdm/ports.json`）或瀏覽器定位；終點於地圖點選（`useRoutePicking.ts` 攔截 `MapView` 點擊）。範圍限於 `fishing_grid` 覆蓋（浮標 120km 內），**不含軍事管制水域**（無開放結構化資料，見免責文案）。
- **部署**：`vite.config.ts` 的 `base` 依 `command` 切換（dev=`/`，build=`/nodass-ocean-dashboard/`），與現行 GitHub Pages 路徑對齊，但**尚未實際部署**——過渡期 `dashboard/*.html` 保留可回退，待人工於分支驗證無衝突後才切換 Pages 來源。
- 已知 gotcha：MapLibre 會在容器加上 `.maplibregl-map` class 蓋過 Tailwind `.absolute`（同特異度、MapLibre CSS 在後），需外層 `absolute inset-0` + 內層 `h-full w-full` 兩層 div 分工，另搭 `ResizeObserver` 呼叫 `map.resize()` 處理 RWD。

## 誠實準確度（寫報告與對使用者溝通時務必照實）
- 高解析 SDM：**空間分塊交叉驗證 AUC 0.75–0.90**（17 種，與隨機 CV 接近，非空間自相關假象）。
- 這是「棲地適合度/出現潛勢」，**不是漁獲量**；目前**無 CPUE 標籤**，無法預測魚量。
- 衛星 archive 止於約 2021；「今日/未來」高解析靠 CWA OCM 數值預報；葉綠素預報用氣候平均。
- 定位：海象與環境可作**參考**（安全以中央氣象署海象/漁業氣象、海巡警報為準）；魚群為**潛勢非保證**。

## 待辦（路線圖）
- **P1（已完成）**：三棲地頁整合為 `platform.html`（iframe 時段切換）。
  - P1.5（已部分完成）：**跨時段魚種選擇保留**已做（postMessage 同步，三子頁適配器 + 平台中繼）。
    尚餘「單一地圖、地圖不重載」之完整深度整合（各子頁資料 schema 不同，屬較大改寫）。
- **P2（已完成風/流/潮）**：未來海象安全層——forecast 頁加 OCM **風速/風向(WS/WD)、潮位(WL)** 圖層與風向量
    （公開免授權，已驗證）；介面參考 ocean.cwa.gov.tw。波浪 Hs 不在 OCM，`fetch_cwa_wave.py` scaffold 就緒，
    需 `.cwa_token`（CWA 開放資料免費金鑰）啟用後接入。
- **P3（已完成信心層）**：**資料信心圖層**已做於 hires 與 forecast（每格到最近出現點距離 → 0–1 信心，
    RdYlGn 色階 + 低信心淡化，已驗證）。GFW 船隊熱區 `fetch_gfw.py` scaffold 就緒，需 `.gfw_token` 啟用。
- **P4（質變，需資料）**：取得漁業署漁獲/VMS/CPUE → 把棲地升級為驗證過的漁獲潛勢/CPUE 預測。
- **航線規劃第二層（已完成，僅「現在」時段）**：`web/` 內 A* 航線規劃（陸地/波高/逆流/魚場/水深/保育區），
    見上方「React 前端」專節。未來時段擴充待 `fetch_cwa_wave.py`（示性波高預報）接入後才有意義；
    軍事管制水域待未來找到結構化開放資料再補。

## gitignored 資料（clone 後會缺，及**下載連結/重抓方式**）
- `data/gbif_taiwan_fish.csv`（魚種出現點）：
  - **可重現重抓（推薦，免金鑰）**：`python fetch_occurrences.py` → 由 GBIF API 重建。
  - GBIF API：`https://api.gbif.org/v1/occurrence/search`（taxonKey + geometry WKT 框 + hasCoordinate）。
  - GBIF 入口（人工檢視/匯出）：https://www.gbif.org/occurrence/search?geometry=POLYGON((118%2020,124%2020,124%2027,118%2027,118%2020))&has_coordinate=true
- `data/全球生物多樣性資料庫(TaiBIF)生物調查資料/`、`臺灣底拖與深海採集資料/`（DwCA）：
  - 來源：TaiBIF IPT https://ipt.taibif.tw 、GBIF 資料集搜尋 https://www.gbif.org/dataset/search（底拖=bottom_trawl、深海=deep-sea-fishes）。
  - 註：**僅 `build_occurrences.py` 需要這些原始檔**；其輸出 `sdm/occurrences.csv` 已隨庫提供，下游 `build_sdm`/`build_hires` 不需原始資料。
- `_sat_cache/`、`_tfrin_pdf/`：由 `fetch_satellite.py`/`fetch_tfrin_env.py` 自動重抓（開放、免金鑰）。
- `nodass.tif`（GEBCO 水深 GeoTIFF，repo 根目錄）：
  - GEBCO 無可直接打 bbox 的公開 API（OPeNDAP 走 CEDA 需帳號），**需人工下載一次**：
    https://download.gebco.net 用官方 bbox 工具下載 `lon 117~123, lat 20~27`、Layer 選
    `Bathymetry`、Format 選 `Geotiff (Data)`，存成 `nodass.tif`。
  - 之後執行 `python build_bathymetry.py` 產生 `sdm/depth_bands.json`：純 Python(tifffile+numpy+
    skimage)分級/取等值線/化簡，不需 QGIS/GDAL。水深是靜態資料，只需做一次。
- `sdm/restricted_zones_manual.json`（選用）：`fetch_conservation_zones.py` 自動解析不出座標的
  漁業資源保育區記錄會印到 stdout，人工查證後可手動整理成同格式（`[{name, county, level, polygon}]`）
  存這個檔，腳本會自動合併進 `sdm/restricted_zones.json`。
- `.nodass_token`：機密，勿外流；目前所有管線都用開放源，不需它。
- `.cwa_token`：CWA 開放資料平台免費金鑰（https://opendata.cwa.gov.tw 申請），`fetch_cwa_wave.py`（示性波高預報）、`fetch_tide.py`（潮汐修正）共用；未設定時兩者安全回傳 None、不寫檔，不影響其餘管線。

## 專案慣例（沿用 owner 的全域規則；協作 agent 請遵守）
- 全部輸出用**繁體中文**（台灣慣用語），**不用 emoji**。
- **未經明確要求，勿新增 `.md` 檔**（本檔與 README 已獲同意）。
- 統計圖表內文字用**英文**；程式註解/說明用繁中。
- 路徑盡量相對；非經要求勿產生測試碼（若有，置於 `tests/`）。
- commit 訊息用 conventional commits（feat/fix/refactor/ui/docs…）。
