"""儀表板共用元件：地理內插工具、響應式樣式、頁籤導覽列。

兩個頁面（極端浪況、漁場魚種）共用此模組，確保版型、字體比例與切換一致。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

_COAST_FILE = Path(__file__).with_name("region_coast.json")


def load_coast() -> str:
    """回傳台灣海岸線 GeoJSON 字串（供前端內嵌，無底圖時自繪陸地）。"""
    try:
        return _COAST_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return '{"type":"FeatureCollection","features":[]}'


def _load_land_polys() -> list[list[tuple[float, float]]]:
    """從精細海岸線 GeoJSON 取出所有陸地多邊形環（本島＋離島），供陸地遮罩用。

    比舊版粗略 12 點外框精準，色塊邊界可貼合真實海岸、不溢出陸地、也不留近岸空缺。
    """
    try:
        gj = json.loads(_COAST_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    polys: list[list[tuple[float, float]]] = []
    for feat in gj.get("features", []):
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "Polygon":
            for ring in coords:
                polys.append([(p[0], p[1]) for p in ring])
        elif gtype == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    polys.append([(p[0], p[1]) for p in ring])
    return polys


# 精細陸地多邊形（程式載入時建立一次），取代舊版粗略外框
LAND_POLYS = _load_land_polys()


def on_land(lon: float, lat: float) -> bool:
    """判斷座標是否落在任一陸地多邊形內（含本島與離島）。"""
    for poly in LAND_POLYS:
        if in_polygon(lon, lat, poly):
            return True
    return False


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def in_polygon(lon: float, lat: float, poly: list[tuple[float, float]]) -> bool:
    """射線法判斷點是否落在多邊形內。"""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > lat) != (yj > lat) and \
                lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def build_grid(points: list[tuple[float, float, float]],
               step: float = 0.1, radius_km: float = 120.0) -> list[dict]:
    """反距離加權 (IDW) 將散點值內插成海域網格。

    points: (lat, lon, value)。僅保留非陸地、且 radius_km 內有觀測點的網格。
    回傳 [{lat, lon, v}]。
    """
    grid: list[dict] = []
    lat = 20.0
    while lat <= 27.0:
        lon = 117.0
        while lon <= 123.0:
            if not on_land(lon, lat):
                num = den = 0.0
                nearest = 1e9
                for plat, plon, pval in points:
                    d = haversine(lat, lon, plat, plon)
                    nearest = min(nearest, d)
                    if d <= radius_km:
                        w = 1.0 / (d * d + 1.0)
                        num += w * pval
                        den += w
                if den > 0 and nearest <= radius_km:
                    grid.append({"lat": round(lat, 3), "lon": round(lon, 3),
                                 "v": round(num / den, 2)})
            lon += step
        lat += step
    return grid


# 響應式樣式：字體採 clamp() 隨視窗縮放，窄螢幕自動單欄堆疊
SHARED_CSS = """
  *{box-sizing:border-box;}
  html{font-size:clamp(13px,0.55vw + 11px,17px);}
  body{margin:0;font-family:"Microsoft JhengHei","Segoe UI",sans-serif;background:#0e1726;color:#e8eef7;}
  header{padding:clamp(10px,1.4vw,16px) clamp(12px,2vw,24px);background:#15233b;border-bottom:1px solid #24344f;}
  header h1{margin:0;font-size:clamp(1.05rem,2.2vw,1.4rem);}
  header .sub{font-size:clamp(0.72rem,1.1vw,0.85rem);color:#9fb3c8;margin-top:4px;}
  .tabs{display:flex;gap:6px;padding:8px clamp(12px,2vw,24px) 0;background:#15233b;border-bottom:1px solid #24344f;flex-wrap:wrap;}
  .tabs a{padding:8px 16px;font-size:clamp(0.78rem,1.2vw,0.92rem);color:#9fb3c8;text-decoration:none;border-radius:8px 8px 0 0;border:1px solid transparent;}
  .tabs a:hover{color:#e8eef7;background:#1c2c46;}
  .tabs a.active{color:#fff;background:#1c2c46;border-color:#2f456b;border-bottom-color:#1c2c46;font-weight:600;}
  .ctrl{padding:8px clamp(12px,2vw,24px);background:#11203a;display:flex;align-items:center;gap:10px;flex-wrap:wrap;border-bottom:1px solid #24344f;}
  .ctrl label{font-size:0.82rem;color:#9fb3c8;}
  .ctrl select{background:#1c2c46;color:#e8eef7;border:1px solid #2f456b;border-radius:6px;padding:6px 10px;font-size:0.9rem;}
  .ctrl input[type=checkbox]{transform:scale(1.15);margin-right:4px;vertical-align:middle;}
  .wrap{display:flex;flex-wrap:wrap;gap:12px;padding:12px;}
  .panel{background:#15233b;border:1px solid #24344f;border-radius:8px;padding:12px;}
  /* 地圖獨佔整列 100% 寬，資訊面板於其下方以自適應網格排列 */
  #map{height:clamp(400px,64vh,640px);flex:1 1 100%;width:100%;min-width:280px;border-radius:8px;}
  .side{flex:1 1 100%;width:100%;display:grid;
        grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;align-items:start;}
  table{width:100%;border-collapse:collapse;font-size:0.82rem;}
  th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #24344f;}
  th{color:#9fb3c8;font-weight:600;}
  tr{cursor:pointer;} tr:hover{background:#1c2c46;}
  .badge{padding:2px 8px;border-radius:10px;color:#fff;font-size:0.78rem;}
  .legend{font-size:0.78rem;color:#9fb3c8;}
  .legend span{display:inline-block;width:11px;height:11px;border-radius:50%;margin:0 4px 0 10px;vertical-align:middle;}
  .kpi{display:flex;gap:10px;flex-wrap:wrap;}
  .kpi div{background:#1c2c46;border-radius:6px;padding:8px 12px;font-size:0.82rem;flex:1 1 auto;text-align:center;}
  .kpi b{font-size:clamp(1rem,1.8vw,1.2rem);display:block;}
  .note{font-size:0.78rem;color:#8aa0b8;line-height:1.6;}
  h3{font-size:clamp(0.9rem,1.4vw,1rem);}
  .chartbox{position:relative;height:200px;width:100%;}
  canvas{background:#0e1726;border-radius:6px;}
  .leaflet-container{background:#0a1a2e;}
  /* 分段按鈕(單選):比下拉更直觀、可一眼看到所有選項 */
  .seg{display:inline-flex;flex-wrap:wrap;gap:4px;}
  .seg button{background:#1c2c46;color:#9fb3c8;border:1px solid #2f456b;border-radius:8px;
    padding:6px 12px;font-size:0.85rem;cursor:pointer;}
  .seg button:hover{color:#e8eef7;}
  .seg button.on{background:#2f6fed;color:#fff;border-color:#2f6fed;font-weight:600;}
  /* 勾選晶片(複選):魚種多時以可捲動晶片清單呈現 */
  .chips{display:flex;flex-wrap:wrap;gap:6px;max-height:120px;overflow:auto;
    padding:6px;background:#11203a;border:1px solid #24344f;border-radius:8px;}
  .chips label{display:inline-flex;align-items:center;gap:5px;background:#1c2c46;
    border:1px solid #2f456b;border-radius:14px;padding:4px 10px;font-size:0.82rem;
    color:#cdd9e5;cursor:pointer;white-space:nowrap;}
  .chips label.on{background:#13361f;border-color:#2e933c;color:#eafff0;}
  .chips input{accent-color:#2e933c;}
  .toolbtn{background:#1c2c46;color:#9fb3c8;border:1px solid #2f456b;border-radius:8px;
    padding:5px 10px;font-size:0.8rem;cursor:pointer;}
  .toolbtn:hover{color:#e8eef7;}
  @media (max-width:760px){ .side{flex:1 1 100%;} #map{flex:1 1 100%;} }
"""


def nav_html(active: str) -> str:
    """產生頁籤導覽列。active 為 'wave'、'fish'、'hires' 或 'fc'。"""
    wave = "active" if active == "wave" else ""
    fish = "active" if active == "fish" else ""
    hires = "active" if active == "hires" else ""
    fc = "active" if active == "fc" else ""
    return (
        '<div class="tabs">'
        f'<a class="{wave}" href="index.html">極端浪況預警</a>'
        f'<a class="{fish}" href="fishing.html">漁場環境與魚種預測</a>'
        f'<a class="{hires}" href="hires.html">高解析小區棲地(衛星)</a>'
        f'<a class="{fc}" href="forecast.html">未來棲地預報(CWA)</a>'
        '</div>'
    )
