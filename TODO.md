# 待辦事項

## 已知阻塞（資料/環境面，非程式邏輯問題）

- **Python 連線 NODASS/CWA 遇 SSL 憑證驗證失敗**：`certificate verify failed: Basic Constraints of
  CA cert not marked critical`，Python 3.13 + OpenSSL 3.5.6 對憑證鏈驗證較嚴格所致，非中間人攻擊、
  非本機獨有（使用者機器上重現相同錯誤）。Node.js 呼叫同樣主機（NODASS API、GBIF、npm registry）
  皆正常，問題侷限在 Python 端。影響範圍：`fetch_buoys.py`、`fetch_ocm_forecast.py`、
  `fetch_conservation_zones.py`、`fetch_tide.py`、`fetch_cwa_wave.py`，**新確認也影響
  `fetch_satellite.py`（NODASS 衛星影像 API）**——`build_hires.py` 重新執行會在 `composite()` 抓場景
  清單時就失敗，非新問題只是首次實測到。目前**暫緩處理**（使用者已明確指示先不管）。待處理時可評估：
  僅對這幾個開放資料主機關閉驗證，或等對方網站自行修正憑證鏈；也可考慮改走 Node.js 中介請求（已驗證
  同主機 Node 不受影響）。
- **`build_sdm_dataset.py`（新增）繞開了這個問題**：不重新呼叫衛星 API，直接讀既有
  `sdm/hires_grid.json`（已算好的 sst/chl/front 網格）+ `occurrences.csv` 統整出
  `sdm/sdm_training_dataset.csv`，17 個魚種的出現點數已跟 `hires_sdm_report.csv` 交叉驗證完全一致。
  等 SSL 問題解決、`build_hires.py` 能重新抓新鮮衛星資料後，其內建的匯出（同一輸出檔）會自然取代這份。
- **`fetch_buoys.py` 失敗時仍會覆寫 `buoy_window.json`**：即使 0/26 站抓取成功，仍會用近乎空的結果
  覆蓋既有資料，屬於未修的既有 bug（尚未影響過正式資料，因每次都用 `git checkout --` 挋回）。
- **`.cwa_token` 尚未申請**：`fetch_cwa_wave.py`（示性波高預報）、`fetch_tide.py`（潮汐修正）兩個
  scaffold 都卡在沒金鑰，無法實測真實回應欄位；`fetch_tide.py` 的 `DATASET_ID`/`parse_records()`
  欄位路徑未經驗證，啟用前需先核對 CWA 開放資料平台實際文件。
- ~~`_bathy_cache/depth_bands.geojson` 尚未產生~~ **已完成**：`nodass.tif`（GEBCO GeoTIFF）已取得，
  `build_bathymetry.py` 改用純 Python(tifffile+numpy+skimage) 直接分級/取等值線，不需 QGIS/GDAL，
  已產生 `sdm/depth_bands.json`（525 個等深帶多邊形）並經瀏覽器驗證圖層正常渲染。
  repo 根目錄同時存在 `gebco_2026_n27.0_s20.0_w117.0_e123.0_geotiff.tif`，經比對與 `nodass.tif`
  像素值完全相同（同一份下載的重複匯出），可考慮之後清掉其中一個以免重複佔用 repo 空間。
- **`sdm/restricted_zones.json` 尚未產生**：`fetch_conservation_zones.py` 因上述 SSL 問題尚未實際
  跑過，避開保育區功能目前無資料可用（不會報錯，僅是沒有區域可避開）。

## 功能面（未來可做，非緊急）

- 未來（CWA 預報）時段的航線規劃：需先有示性波高預報（`fetch_cwa_wave.py` 接上金鑰後）才有意義，
  目前僅「現在」時段支援航線規劃。
- 軍事管制水域：v1 刻意略過，未找到結構化開放資料，僅在免責文案提醒使用者。
- 潮位修正目前為「單一測站/單一數值」修正整條航線的水深門檻，非逐格逐時模擬；若之後要做更精細的
  時空潮位場，需先確認是否有可用的公開潮位傳播網格資料（初步查證台灣無此類公開資料）。
- `routeCells.ts` 的等深帶判斷是每個規劃格點對每個等深帶多邊形做 point-in-polygon（bbox 先粗篩）；
  目前 525 個多邊形、約 6300 個頂點屬合理量級。若之後換更高解析度的 GEBCO 來源，可調
  `build_bathymetry.py` 的 `DOWNSAMPLE`/`SIMPLIFY_TOL_DEG` 兩個常數控制頂點數上限。
