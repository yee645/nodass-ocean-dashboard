"""Global Fishing Watch(GFW)漁撈努力熱區介接(scaffold，需免費 API 金鑰)。

用途(P3)：以 AIS 推估的漁撈努力(fishing effort)網格，作為「環境棲地潛勢」與
「實際有人在哪作業」之間的橋樑，疊為一圖層與棲地對照。屬 AIS 推估、非實測漁獲。

金鑰：至 https://globalfishingwatch.org/our-apis/ 免費註冊取得 API token，
存於專案根 `.gfw_token`(單行，已列入 .gitignore，勿外流)。無金鑰時安全回傳 None。

API：GFW 4Wings report(v3)，以 bbox + 日期區間取 fishing-effort 網格聚合。
端點與參數以官方文件為準(本檔提供通用呼叫骨架，欄位/版本可能調整)。

注意：本模組為 scaffold，未在本庫實測(無金鑰)。啟用前請以 main() 驗證回傳結構，
再轉成 0.05° 網格疊圖。資料來源須註明：Global Fishing Watch(AIS 推估漁撈努力)。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parent / ".gfw_token"
API_ROOT = "https://gateway.api.globalfishingwatch.org/v3"
# 台灣周邊海域(west,south,east,north)，與其他管線一致的環島範圍
TAIWAN_BBOX = (118.0, 21.0, 124.0, 26.5)
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def load_token() -> str | None:
    """讀取 .gfw_token；不存在或空白回傳 None(呼叫端據此優雅跳過)。"""
    try:
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        return tok or None
    except FileNotFoundError:
        return None


def fetch_effort(date1: str, date2: str, bbox=TAIWAN_BBOX,
                 timeout: int = 45) -> dict | None:
    """取 GFW fishing-effort 聚合(4Wings report)。無金鑰或失敗回傳 None。

    date1/date2：YYYY-MM-DD 區間。bbox：(west,south,east,north)。
    回傳原始 JSON(呼叫端再轉網格)。實際參數請對照 GFW v3 文件微調。
    """
    token = load_token()
    if not token:
        print("略過 GFW：找不到 .gfw_token(需至 globalfishingwatch.org 申請免費金鑰)")
        return None
    w, s, e, n = bbox
    geojson = {"type": "Polygon", "coordinates": [[
        [w, s], [e, s], [e, n], [w, n], [w, s]]]}
    query = {
        "spatial-resolution": "LOW",
        "temporal-resolution": "ENTIRE",
        "datasets[0]": "public-global-fishing-effort:latest",
        "date-range": f"{date1},{date2}",
        "format": "JSON",
    }
    url = f"{API_ROOT}/4wings/report?" + urllib.parse.urlencode(query)
    body = json.dumps({"geojson": geojson}).encode("utf-8")
    headers = {**UA, "Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    try:
        raw = urllib.request.urlopen(
            urllib.request.Request(url, data=body, headers=headers),
            timeout=timeout).read()
        return json.loads(raw.decode("utf-8", "ignore"))
    except Exception as ex:  # noqa: BLE001
        print("GFW 請求失敗：", type(ex).__name__, str(ex)[:100])
        return None


if __name__ == "__main__":
    d = fetch_effort("2024-01-01", "2024-12-31")
    if d is None:
        print("無資料(缺金鑰或請求失敗)。設定 .gfw_token 後重試。")
    else:
        print("GFW 回應 keys:", list(d.keys())[:8] if isinstance(d, dict) else type(d))
