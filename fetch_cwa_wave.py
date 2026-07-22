"""CWA 開放資料波浪(示性波高 Hs)預報介接與正規化(需免費 API 金鑰)。

用途(P2 第二階段)：補上 OCM 沒有的「示性波高(Hs)」未來預報，與既有海象安全層(風/流/潮)
整合，提供出航前波況參考。OCM 海流模式不含波浪，故波浪須另接中央氣象署海象/沿海波浪資料集。

金鑰：至 https://opendata.cwa.gov.tw 免費註冊取得 Authorization 金鑰，
存於專案根 `.cwa_token`(單行，已列入 .gitignore，勿外流)。無金鑰時本模組安全回傳 None，
呼叫端(build_forecast)據此優雅跳過，頁面維持現況、不產生波浪圖層(零回歸)。

資料流：
  fetch_wave()  取原始 datastore JSON(需金鑰、需網路)
  normalize()   解析為測站清單 [{name, lat, lon, times:[{valid, hs, dir}]}]
  to_grid()     以反距離加權(IDW)把各測站 Hs 內插到 forecast 網格(逐預報時段)
  load_or_fetch() 有快取(dashboard/wave_forecast.json)優先用快取，否則抓取並寫快取

備註：
  - 資料集 F-A0021-001(臺灣各沿海預報)提供沿海海面「浪高(WaveHeight)」，其位置為
    命名海區而非座標，本模組以 COASTAL_ZONES 對照表給定各海區代表座標供 IDW。
    若改用具經緯度的測站型資料集，normalize() 會優先採用資料內的 lat/lon。
  - normalize()/to_grid() 已以符合 CWA datastore schema 的 mock 驗證；
    實際欄位/dataid 請依平台文件微調 DATASET_ID 與 _WAVE_ELEMENT_NAMES。
  - 資料來源須註明：中央氣象署開放資料。出海安全正式以官方海象/漁業氣象與海巡署警報為準。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from dashboard_common import haversine

TOKEN_FILE = Path(__file__).resolve().parent / ".cwa_token"
CACHE_FILE = Path(__file__).resolve().parent / "dashboard" / "wave_forecast.json"
API_ROOT = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
DATASET_ID = "F-A0021-001"          # 臺灣各沿海預報(含浪高)；實際以平台公告為準，可調整
UA = {"User-Agent": "Mozilla/5.0"}

# 浪高要素在不同資料集/語系下的可能名稱(大小寫不敏感比對)
_WAVE_ELEMENT_NAMES = ("waveheight", "wave", "浪高", "波高", "示性波高", "wh")
_DIR_ELEMENT_NAMES = ("wavedirection", "浪向", "波向", "wd")

# 臺灣各沿海海區代表座標(近海代表點；供命名海區的 Hs 做 IDW 內插)。
# 座標為各海區外海代表位置，非行政界；僅用於把海區 Hs 灑到 forecast 網格。
COASTAL_ZONES: dict[str, tuple[float, float]] = {
    "臺灣北部海面": (25.5, 121.5),
    "臺灣東北部海面": (25.4, 122.3),
    "臺灣東部海面": (23.8, 121.9),
    "臺灣東南部海面": (22.4, 121.4),
    "臺灣南部海面": (21.9, 120.7),
    "臺灣西南部海面": (22.4, 120.0),
    "臺灣中部海面": (24.0, 120.1),
    "臺灣西北部海面": (25.0, 120.9),
    "臺灣海峽北部": (25.0, 120.0),
    "臺灣海峽南部": (23.0, 119.3),
    "臺灣海峽": (24.0, 119.6),
    "巴士海峽": (21.5, 121.0),
    "東沙島海面": (20.7, 116.7),
    "澎湖海面": (23.5, 119.5),
    "蘭嶼綠島海面": (22.4, 121.5),
}


def load_token() -> str | None:
    """讀取 .cwa_token；不存在或空白回傳 None(呼叫端據此優雅跳過)。"""
    try:
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        return tok or None
    except FileNotFoundError:
        return None


def fetch_wave(dataset_id: str = DATASET_ID, params: dict | None = None,
               timeout: int = 30) -> dict | None:
    """呼叫 CWA datastore 取波浪/海象預報原始 JSON。無金鑰或失敗回傳 None。"""
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


def _num(text) -> float | None:
    """從字串/數值取第一個數字；範圍(如 '2~3' 或 '2 到 3')取中點。無數字回傳 None。"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    nums = re.findall(r"-?\d+(?:\.\d+)?", str(text))
    if not nums:
        return None
    vals = [float(n) for n in nums]
    return sum(vals) / len(vals) if len(vals) >= 2 else vals[0]


def _locations(records: dict) -> list:
    """相容多種 datastore 結構，回傳 location 物件清單。"""
    if not isinstance(records, dict):
        return []
    # 常見：records.locations.location[]；亦見 records.location[] 或 records.Locations.Location[]
    for outer in ("locations", "Locations", "location", "Location"):
        node = records.get(outer)
        if isinstance(node, list):
            return node
        if isinstance(node, dict):
            for inner in ("location", "Location"):
                if isinstance(node.get(inner), list):
                    return node[inner]
    return []


def _elements(loc: dict) -> list:
    for key in ("weatherElement", "WeatherElement", "weatherElements"):
        if isinstance(loc.get(key), list):
            return loc[key]
    return []


def _element_name(el: dict) -> str:
    for key in ("elementName", "ElementName", "name"):
        if el.get(key):
            return str(el[key])
    return ""


def _time_entries(el: dict) -> list:
    for key in ("time", "Time", "times"):
        if isinstance(el.get(key), list):
            return el[key]
    return []


def _entry_valid(t: dict) -> str | None:
    for key in ("startTime", "StartTime", "dataTime", "DataTime", "endTime", "EndTime"):
        if t.get(key):
            return str(t[key])
    return None


def _entry_value(t: dict) -> float | None:
    ev = t.get("elementValue") or t.get("ElementValue") or t.get("value")
    if isinstance(ev, list):
        for item in ev:
            if isinstance(item, dict):
                v = _num(item.get("value") or item.get("Value") or item.get("measures"))
                if v is not None:
                    return v
            else:
                v = _num(item)
                if v is not None:
                    return v
        return None
    if isinstance(ev, dict):
        return _num(ev.get("value") or ev.get("Value") or ev.get("measures"))
    return _num(ev)


def _entry_value_raw(t: dict):
    """回傳時段的原始值(不做數值轉換)；供波向(可能為方位詞或度數)保留原文。"""
    ev = t.get("elementValue") or t.get("ElementValue") or t.get("value")
    if isinstance(ev, list):
        for item in ev:
            if isinstance(item, dict):
                v = item.get("value") or item.get("Value") or item.get("measures")
                if v not in (None, ""):
                    return v
            elif item not in (None, ""):
                return item
        return None
    if isinstance(ev, dict):
        return ev.get("value") or ev.get("Value") or ev.get("measures")
    return ev


def _match(name: str, wanted: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(w in low for w in wanted)


def normalize(raw: dict) -> list[dict]:
    """把 CWA datastore JSON 解析為測站清單。

    回傳：[{name, lat, lon, times:[{valid, hs, dir}]}]；
    座標優先取資料內 lat/lon，否則以 COASTAL_ZONES 依海區名對照(取不到則略過該站)。
    """
    records = (raw or {}).get("records") or (raw or {}).get("Records") or {}
    out: list[dict] = []
    for loc in _locations(records):
        name = ""
        for key in ("locationName", "LocationName", "name", "Name"):
            if loc.get(key):
                name = str(loc[key])
                break
        lat = _num(loc.get("lat") or loc.get("Lat") or loc.get("latitude"))
        lon = _num(loc.get("lon") or loc.get("Lon") or loc.get("longitude"))
        if (lat is None or lon is None) and name in COASTAL_ZONES:
            lat, lon = COASTAL_ZONES[name]
        if lat is None or lon is None:
            continue
        hs_el = dir_el = None
        for el in _elements(loc):
            en = _element_name(el)
            if hs_el is None and _match(en, _WAVE_ELEMENT_NAMES):
                hs_el = el
            elif dir_el is None and _match(en, _DIR_ELEMENT_NAMES):
                dir_el = el
        if hs_el is None:
            continue
        dir_by_valid: dict[str, float | None] = {}
        for t in _time_entries(dir_el or {}):
            v = _entry_valid(t)
            if v is not None:
                dir_by_valid[v] = _entry_value_raw(t)
        times = []
        for t in _time_entries(hs_el):
            valid = _entry_valid(t)
            hs = _entry_value(t)
            if valid is None or hs is None:
                continue
            times.append({"valid": valid, "hs": round(hs, 2),
                          "dir": dir_by_valid.get(valid)})
        if times:
            out.append({"name": name, "lat": round(lat, 3), "lon": round(lon, 3),
                        "times": times})
    return out


def _nearest_hs(station: dict, valid_prefix: str) -> float | None:
    """取測站在指定預報時段的 Hs：優先前綴(YYYY-MM-DD)相符者，否則取第一筆。"""
    for t in station["times"]:
        if str(t["valid"]).startswith(valid_prefix):
            return t["hs"]
    return station["times"][0]["hs"] if station["times"] else None


def to_grid(stations: list[dict], cells: list[dict],
            lead_valids: dict[int, str], radius_km: float = 180.0,
            power: float = 2.0) -> dict[str, list]:
    """把測站 Hs 以 IDW 內插到 forecast 網格(逐預報時段)。

    cells：[{lat, lon}, ...]；lead_valids：{lead_day: 'YYYY-MM-DD'}(對應預報有效時間)。
    回傳 {str(lead_day): [hs 或 None per cell]}；無有效測站的時段回傳整列 None。
    """
    out: dict[str, list] = {}
    for dday, prefix in lead_valids.items():
        pts = [(s["lat"], s["lon"], _nearest_hs(s, prefix)) for s in stations]
        pts = [(la, lo, hs) for la, lo, hs in pts if hs is not None]
        col: list[float | None] = []
        for c in cells:
            num = den = 0.0
            near = 1e9
            for la, lo, hs in pts:
                d = haversine(c["lat"], c["lon"], la, lo)
                near = min(near, d)
                if d <= radius_km:
                    wgt = 1.0 / (d ** power + 1.0)
                    num += wgt * hs
                    den += wgt
            col.append(round(num / den, 2) if den > 0 and near <= radius_km else None)
        out[str(dday)] = col
    return out


def load_or_fetch(dataset_id: str = DATASET_ID,
                  cache: Path = CACHE_FILE) -> list[dict] | None:
    """有快取優先用快取，否則抓取+正規化並寫快取。皆失敗回傳 None。"""
    if cache.exists():
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            stations = payload.get("stations") if isinstance(payload, dict) else payload
            if stations:
                return stations
        except Exception:  # noqa: BLE001
            pass
    raw = fetch_wave(dataset_id)
    if raw is None:
        return None
    stations = normalize(raw)
    if not stations:
        print("CWA 波浪：正規化後無有效測站(檢查 dataid 或要素名稱)")
        return None
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps({"source": "中央氣象署開放資料 " + dataset_id,
                                 "stations": stations},
                                ensure_ascii=False, separators=(",", ":")),
                     encoding="utf-8")
    print(f"CWA 波浪：{len(stations)} 站已快取 -> {cache.name}")
    return stations


if __name__ == "__main__":
    st = load_or_fetch()
    if not st:
        print("無資料(缺金鑰或請求失敗)。設定 .cwa_token 後重試。")
    else:
        print(f"波浪測站 {len(st)} 站；示例：")
        for s in st[:3]:
            hs = [t["hs"] for t in s["times"]]
            print(f"  {s['name']} ({s['lat']},{s['lon']})  Hs {min(hs)}~{max(hs)} m  {len(hs)} 時段")
