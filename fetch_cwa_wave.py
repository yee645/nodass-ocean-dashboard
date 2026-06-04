"""CWA 開放資料波浪預報介接(scaffold，需免費 API 金鑰)。

用途(P2 第二階段)：補上 OCM 沒有的「示性波高(Hs)」未來預報，與既有海象安全層(風/流/潮)
整合，提供出航前波況參考。OCM 海流模式不含波浪，故波浪須另接中央氣象署波浪/海象資料集。

金鑰：至 https://opendata.cwa.gov.tw 免費註冊取得 Authorization 金鑰，
存於專案根 `.cwa_token`(單行，已列入 .gitignore，勿外流)。無金鑰時本模組安全回傳 None。

資料集：CWA 開放資料平台「海象/波浪預報」系列(dataid 視平台公告調整，例如沿海風浪預報)。
本檔以通用 datastore 介面實作；實際 dataid 與欄位請依平台文件設定 DATASET_ID。

注意：本模組為 scaffold，未在本庫實測(無金鑰)。啟用前請先以 main() 驗證回傳結構，
再接入 build_forecast.py 的海象安全層。資料來源須註明：中央氣象署開放資料。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parent / ".cwa_token"
API_ROOT = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
DATASET_ID = "F-A0021-001"          # 預設：海面風力與浪高預報(實際以平台公告為準，可調整)
UA = {"User-Agent": "Mozilla/5.0"}


def load_token() -> str | None:
    """讀取 .cwa_token；不存在或空白回傳 None(呼叫端據此優雅跳過)。"""
    try:
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        return tok or None
    except FileNotFoundError:
        return None


def fetch_wave(dataset_id: str = DATASET_ID, params: dict | None = None,
               timeout: int = 30) -> dict | None:
    """呼叫 CWA datastore 取波浪/海象預報 JSON。無金鑰或失敗回傳 None。

    params：額外查詢參數(如測站、時間、要素)，依資料集文件設定。
    """
    token = load_token()
    if not token:
        print("略過 CWA 波浪：找不到 .cwa_token(需至 opendata.cwa.gov.tw 申請免費金鑰)")
        return None
    query = {"Authorization": token, "format": "JSON"}
    if params:
        query.update(params)
    url = f"{API_ROOT}/{dataset_id}?" + urllib.parse.urlencode(query)
    try:
        raw = urllib.request.urlopen(
            urllib.request.Request(url, headers=UA), timeout=timeout).read()
        data = json.loads(raw.decode("utf-8", "ignore"))
        if str(data.get("success", "")).lower() != "true":
            print("CWA 波浪回應 success != true，請檢查 dataid/金鑰權限")
            return None
        return data
    except Exception as e:  # noqa: BLE001
        print("CWA 波浪請求失敗：", type(e).__name__, str(e)[:80])
        return None


if __name__ == "__main__":
    d = fetch_wave()
    if d is None:
        print("無資料(缺金鑰或請求失敗)。設定 .cwa_token 後重試。")
    else:
        recs = d.get("records", {})
        print("CWA 波浪 records keys:", list(recs.keys())[:8])
