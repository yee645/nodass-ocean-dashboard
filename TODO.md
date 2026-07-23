# 待辦事項

## 已知阻塞（資料/環境面，非程式邏輯問題）

- **Python 連線 NODASS/CWA 遇 SSL 憑證驗證失敗**：`certificate verify failed: Basic Constraints of
  CA cert not marked critical`，Python 3.13 + OpenSSL 3.5.6 對憑證鏈驗證較嚴格所致，非中間人攻擊、
  非本機獨有（使用者機器上重現相同錯誤）。Node.js 呼叫同樣主機（NODASS API、GBIF、npm registry）
  皆正常，問題侷限在 Python 端。影響範圍：`fetch_buoys.py`、`fetch_ocm_forecast.py`、
  `fetch_conservation_zones.py`、`fetch_tide.py`、`fetch_cwa_wave.py`。目前**暫緩處理**（使用者已
  明確指示先不管）。待處理時可評估：僅對這幾個開放資料主機關閉驗證，或等對方網站自行修正憑證鏈。
- **`fetch_buoys.py` 失敗時仍會覆寫 `buoy_window.json`**：即使 0/26 站抓取成功，仍會用近乎空的結果
  覆蓋既有資料，屬於未修的既有 bug（尚未影響過正式資料，因每次都用 `git checkout --` 挋回）。
- **`.cwa_token` 尚未申請**：`fetch_cwa_wave.py`（示性波高預報）、`fetch_tide.py`（潮汐修正）兩個
  scaffold 都卡在沒金鑰，無法實測真實回應欄位；`fetch_tide.py` 的 `DATASET_ID`/`parse_records()`
  欄位路徑未經驗證，啟用前需先核對 CWA 開放資料平台實際文件。
- **`_bathy_cache/gebco.asc` 尚未下載**：`build_bathymetry.py` 無法產生 `sdm/bathymetry.json`，
  下載步驟見 CLAUDE.md「gitignored 資料」章節。
- **`sdm/restricted_zones.json` 尚未產生**：`fetch_conservation_zones.py` 因上述 SSL 問題尚未實際
  跑過，避開保育區功能目前無資料可用（不會報錯，僅是沒有區域可避開）。

## 功能面（未來可做，非緊急）

- 未來（CWA 預報）時段的航線規劃：需先有示性波高預報（`fetch_cwa_wave.py` 接上金鑰後）才有意義，
  目前僅「現在」時段支援航線規劃。
- 軍事管制水域：v1 刻意略過，未找到結構化開放資料，僅在免責文案提醒使用者。
- 潮位修正目前為「單一測站/單一數值」修正整條航線的水深門檻，非逐格逐時模擬；若之後要做更精細的
  時空潮位場，需先確認是否有可用的公開潮位傳播網格資料（初步查證台灣無此類公開資料）。
