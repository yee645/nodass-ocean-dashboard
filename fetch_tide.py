"""CWA 開放資料潮汐預報介接(scaffold，需免費 API 金鑰)。

用途：航線規劃吃水限制目前只比對 GEBCO 靜態(平均海平面)水深，退潮時淺灘可能
比標示更淺。本模組抓潮汐測站目前潮位，供 web 端做「單點潮位修正」
(depth + tideOffsetM < draftM)，非全網格逐時模擬。

金鑰：與 fetch_cwa_wave.py 共用 `.cwa_token`(至 https://opendata.cwa.gov.tw 免費申請，
存於專案根，已列入 .gitignore)。無金鑰時安全回傳 None、不寫檔。

資料集：CWA 開放資料平台「潮汐預報」系列，dataid 視平台公告調整，本檔為 scaffold，
未在本庫實測(無金鑰)。啟用前請先以 main() 驗證回傳結構是否含測站座標與潮位數值，
再視實際欄位調整 parse_records()。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from fetch_cwa_wave import load_token, API_ROOT  # 共用金鑰讀取與 API 根路徑

OUT = Path(__file__).resolve().parent / "sdm" / "tide.json"
DATASET_ID = "F-A0021-001"  # 預設：潮汐預報(實際以平台公告為準，啟用前請核對)
UA = {"User-Agent": "Mozilla/5.0"}


def fetch_tide(dataset_id: str = DATASET_ID, timeout: int = 30) -> dict | None:
    """呼叫 CWA datastore 取潮汐預報 JSON。無金鑰或失敗回傳 None。"""
    token = load_token()
    if not token:
        print("略過 CWA 潮汐：找不到 .cwa_token(需至 opendata.cwa.gov.tw 申請免費金鑰)")
        return None
    query = {"Authorization": token, "format": "JSON"}
    url = f"{API_ROOT}/{dataset_id}?" + urllib.parse.urlencode(query)
    try:
        raw = urllib.request.urlopen(
            urllib.request.Request(url, headers=UA), timeout=timeout).read()
        data = json.loads(raw.decode("utf-8", "ignore"))
        if str(data.get("success", "")).lower() != "true":
            print("CWA 潮汐回應 success != true，請檢查 dataid/金鑰權限")
            return None
        return data
    except Exception as e:  # noqa: BLE001
        print("CWA 潮汐請求失敗：", type(e).__name__, str(e)[:80])
        return None


def parse_records(data: dict) -> list[dict]:
    """把 CWA 回應轉成 [{name, lat, lon, tideM}]；欄位路徑未經實測，需依實際回應調整。"""
    stations = data.get("records", {}).get("Station", [])
    out = []
    for st in stations:
        try:
            name = st["StationName"]
            lat = float(st["StationLatitude"])
            lon = float(st["StationLongitude"])
            tide_now = st["TideForecasts"][0]["TideHeight"]
            out.append({"name": name, "lat": lat, "lon": lon, "tideM": round(float(tide_now), 2)})
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return out


def main() -> None:
    data = fetch_tide()
    if data is None:
        print("無資料(缺金鑰或請求失敗)。設定 .cwa_token 後重試。")
        return
    stations = parse_records(data)
    if not stations:
        print("解析不到任何測站，請先核對 DATASET_ID 與 parse_records() 欄位路徑。")
        return
    OUT.write_text(json.dumps(stations, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"寫入 {OUT}，共 {len(stations)} 個測站")


if __name__ == "__main__":
    main()
