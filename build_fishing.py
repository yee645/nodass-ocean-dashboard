"""題目 0：NODASS 開放浮標 → 漁場環境 + 經濟魚種棲地預測（連續、即時、含移動）。

精確範圍：以 0.05° 細網格 IDW 內插 SST，逐網格算魚種棲地適合度（canvas 算繪）。
即時更新：執行 live_update.py（可搭排程）重抓最新浮標資料重建，使用者重整頁面即見最新。
魚群位置與移動：
  - 魚群熱區 = 適合度高的相鄰網格連通分群後聯集而成的不規則區域。
  - 漂移方向 = 該熱區內各格浮標實測表層海流向量平均（魚群隨流移動）。
  - 棲地趨勢 = 近 6 小時 SST 變化（升/降溫 → 暖/冷水魚種棲地擴張或收縮）。
魚種習性見 species_traits.py。完整葉綠素/歷史需會員管制資料權限。
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

from dashboard_common import (INFO_MODAL_JS, SHARED_CSS, haversine, info_modal,
                              load_coast, nav_html, on_land)
from species_traits import SPECIES, suitability

DATA_DIR = Path(__file__).resolve().parent      # 專案根(相對於本檔)，取代舊硬編絕對路徑
SRC = DATA_DIR / "buoy_window.json"
OUT = DATA_DIR / "dashboard" / "fishing.html"

GRID_STEP = 0.05      # 細網格解析度（度）
RADIUS_KM = 120.0     # 內插半徑（超出不外推）


def latest(recs: list[dict], field: str) -> float | None:
    vals = [(r.get("time"), r.get(field)) for r in recs if r.get(field) is not None]
    vals.sort()
    return vals[-1][1] if vals else None


def sst_series(recs: list[dict]) -> list[dict]:
    out = []
    for r in sorted(recs, key=lambda x: x.get("time") or ""):
        v = r.get("Sea_Temperature")
        t = r.get("DateTime") or r.get("time")
        if v is not None and t is not None:
            out.append({"t": t, "v": float(v)})
    return out


def sst_trend(recs: list[dict]) -> float | None:
    """近 6 小時海溫線性趨勢（°C/hr）。"""
    s = sst_series(recs)[-7:]
    if len(s) < 3:
        return None
    n = len(s)
    xs = list(range(n))
    ys = [p["v"] for p in s]
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return round(sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / den, 3)


def current_uv(recs: list[dict]) -> tuple[float, float] | None:
    """最新表層海流向量 (東分量 u, 北分量 v)，單位 m/s。方向為流向(去向)。"""
    sp = latest(recs, "Current_Speed")
    di = latest(recs, "Current_Direction")
    if sp is None or di is None:
        return None
    rad = math.radians(di)
    return (sp * math.sin(rad), sp * math.cos(rad))


def level_color(score: float) -> tuple[str, str]:
    if score >= 60:
        return "高潛勢", "#d7263d"
    if score >= 35:
        return "中潛勢", "#f0a202"
    return "低潛勢", "#2e933c"


def idw(points: list[tuple[float, float, float]], lat: float, lon: float):
    num = den = 0.0
    nearest = 1e9
    for plat, plon, pval in points:
        d = haversine(lat, lon, plat, plon)
        nearest = min(nearest, d)
        if d <= RADIUS_KM:
            w = 1.0 / (d * d + 1.0)
            num += w * pval
            den += w
    if den > 0 and nearest <= RADIUS_KM:
        return num / den
    return None


def build_combined_grid(sst_pts, u_pts, v_pts, tr_pts) -> list[dict]:
    """細網格內插 SST、海流 u/v、SST 趨勢；網格集合由 SST 可內插範圍決定。"""
    grid = []
    lat = 20.0
    while lat <= 27.0:
        lon = 117.0
        while lon <= 123.0:
            if not on_land(lon, lat):
                sst = idw(sst_pts, lat, lon)
                if sst is not None:
                    cell = {"lat": round(lat, 3), "lon": round(lon, 3),
                            "v": round(sst, 2)}
                    u = idw(u_pts, lat, lon)
                    w = idw(v_pts, lat, lon)
                    tr = idw(tr_pts, lat, lon)
                    if u is not None and w is not None:
                        cell["u"] = round(u, 3)
                        cell["w"] = round(w, 3)
                    if tr is not None:
                        cell["tr"] = round(tr, 3)
                    grid.append(cell)
            lon += GRID_STEP
        lat += GRID_STEP
    return grid


def build() -> None:
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    month = datetime.now().month

    stations = []
    for obj in raw.values():
        recs = obj["records"]
        m = obj["meta"]
        uv = current_uv(recs)
        stations.append({
            "id": m["StationID"], "name": m["StationNameLocal"],
            "charge": m["Charge"], "lat": m["lat"], "lon": m["lon"],
            "sst": latest(recs, "Sea_Temperature"),
            "current": latest(recs, "Current_Speed"),
            "u": uv[0] if uv else None, "w": uv[1] if uv else None,
            "trend": sst_trend(recs),
            "sst_series": sst_series(recs),
        })
    sst_st = [s for s in stations if s["sst"] is not None]

    for s in sst_st:
        grad = 0.0
        for o in sst_st:
            if o is s:
                continue
            d = haversine(s["lat"], s["lon"], o["lat"], o["lon"])
            if 0 < d <= 200:
                grad = max(grad, abs(s["sst"] - o["sst"]) / d * 100)
        s["front"] = round(grad, 2)
        cur = s["current"] or 0.0
        score = 70 * min(1.0, grad / 3.0) + 30 * min(1.0, cur / 0.8)
        s["fish_score"] = round(min(100.0, score), 1)
        s["level"], s["color"] = level_color(s["fish_score"])
        s["species"] = {sp["name"]: suitability(s["sst"], sp, month) for sp in SPECIES}

    # 時間軸：對齊各站海溫時序（前向填補），供前端逐時重算 SST 與棲地熱區
    times = sorted({p["t"] for s in sst_st for p in s["sst_series"]})
    for s in sst_st:
        mp = {p["t"]: p["v"] for p in s["sst_series"]}
        last = None; arr = []
        for t in times:
            if t in mp:
                last = mp[t]
            arr.append(last)
        s["sst_t"] = arr

    sst_st.sort(key=lambda s: s["fish_score"], reverse=True)

    sst_pts = [(s["lat"], s["lon"], s["sst"]) for s in sst_st]
    u_pts = [(s["lat"], s["lon"], s["u"]) for s in stations if s.get("u") is not None]
    v_pts = [(s["lat"], s["lon"], s["w"]) for s in stations if s.get("w") is not None]
    tr_pts = [(s["lat"], s["lon"], s["trend"]) for s in stations if s.get("trend") is not None]
    grid = build_combined_grid(sst_pts, u_pts, v_pts, tr_pts)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = (TPL.replace("__CSS__", SHARED_CSS)
               .replace("__NAV__", nav_html("fish"))
               .replace("__MODAL__", info_modal("關於本頁與資料說明", FISH_MODAL_BODY))
               .replace("__MODALJS__", INFO_MODAL_JS)
               .replace("__DATA__", json.dumps(sst_st, ensure_ascii=False))
               .replace("__SPECIES__", json.dumps(SPECIES, ensure_ascii=False))
               .replace("__GRID__", json.dumps(grid, ensure_ascii=False))
               .replace("__TIMES__", json.dumps(times, ensure_ascii=False))
               .replace("__COAST__", load_coast())
               .replace("__MONTH__", str(month))
               .replace("__STEP__", str(GRID_STEP))
               .replace("__TS__", generated))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    # 另輸出 JSON 供 React 前端(web/)fetch，內容與內嵌資料一致（功能零退化）
    payload = {
        "meta": {"month": month, "step": GRID_STEP, "generated": generated},
        "species": SPECIES,
        "stations": sst_st,
        "grid": grid,
        "times": times,
    }
    out_json = DATA_DIR / "sdm" / "fishing_grid.json"
    out_json.parent.mkdir(exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")

    print(f"已產生 {OUT}  有效站數={len(sst_st)}  魚種={len(SPECIES)}  "
          f"細網格={len(grid)}(step={GRID_STEP}°)  海流站={len(u_pts)}  月份={month}")


FISH_MODAL_BODY = """
  <div class="note">
  <b>魚種棲地適合度（0–100）</b>：適溫窗梯形隸屬函數 × 季節因子，將浮標 SST 以 IDW 內插成 0.05° 連續海域網格；色塊邊界已用精細海岸線遮罩，僅顯示海域、不溢出陸地。<br/><br/>
  <b>魚群熱區（金色高亮區）</b>：在適合度 ≥70 的海域網格中，把彼此相鄰的格子做連通分群並聯集成一塊不規則高亮區（沿實際 0.05° 格邊界，不圈進非熱區或陸地），整塊只標一處。<b>可能移動方位（藍色箭頭與標籤）</b>：取該熱區內各格浮標實測表層海流向量平均，自區域質心畫出單一箭頭，代表魚群可能隨流移動的去向，箭頭越長流速越大。點地圖任一點可查該處經緯度與海況。<br/><br/>
  <b>棲地趨勢</b>：近 6 小時 SST 變化；升溫使暖水魚種適宜帶向北/外擴、冷水魚種收縮，反之亦然。<br/>
  <b>無色塊區域</b>：代表該海域不在開放浮標的有效內插範圍（最近浮標逾 120km），本系統不外推，以維持結果可信；東沙、南沙太平島等遠域因無鄰近開放浮標故無資料。<br/>
  <b>即時</b>：執行 live_update.py（可搭排程）重抓最新浮標資料並重建，重整頁面即見最新。完整葉綠素/歷史需會員權限。對齊 SDG 14。
  </div>
"""


TPL = r"""<!DOCTYPE html>
<html lang="zh-Hant" class="cwa">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NODASS 漁場環境與經濟魚種棲地預測</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>__CSS__
  /* 魚群熱點移動方位標籤：浮於金色熱點圈上方 */
  .hotlabel{white-space:nowrap;font-size:10px;color:#ffd000;font-weight:700;text-align:center;
    text-shadow:0 0 3px #000,0 0 3px #000;}
  /* 海流漂移箭頭：向上三角形，依流向旋轉 */
  .drift{width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;
    border-bottom:10px solid #7fd4ff;filter:drop-shadow(0 0 2px #000);}
  /* 圖例樣本（class 選擇器特異度高於共用樣式的 .legend span，可覆寫尺寸） */
  .legend .bar{width:80px;height:10px;border-radius:3px;
    background:linear-gradient(90deg,rgb(46,147,108),rgb(240,162,2),rgb(215,38,61));}
  .legend .lg-zone{display:inline-block;width:14px;height:11px;border-radius:2px;
    border:1.5px solid #ffd000;background:rgba(255,208,0,.18);}
  .legend .lg-arrow{width:0;height:0;border-radius:0;border-left:5px solid transparent;
    border-right:5px solid transparent;border-bottom:11px solid #7fd4ff;}
</style>
<script>if(window.top!==window.self)document.documentElement.classList.add('embedded');</script>
</head>
<body>
<button class="panel-reopen" id="leftReopen" title="開啟資訊" aria-label="開啟資訊">&#9776;</button>
<div class="leftpanel" id="leftPanel">
  <div class="lpane-head">
    <div class="lpane-title">NODASS 漁場環境與經濟魚種棲地預測</div>
    <button class="lpane-x" id="leftCollapse" title="收合" aria-label="收合">&times;</button>
  </div>
  <div class="lpane-sub">海溫鋒面 × 海流 × 魚種適溫窗｜連續內插 0.05°｜NODASS 開放浮標 API｜產生 __TS__（第 __MONTH__ 月）</div>
  __NAV__
</div>
<div class="stage">
  <div id="map"></div>
  <div class="layerpanel" id="layerPanel">
    <div class="lp-head" id="lpHead">
      <h2>魚種圖層</h2>
      <button class="infobtn" id="infoBtn" title="說明" aria-label="說明">i</button>
      <span class="lp-arrow">&#9662;</span>
    </div>
    <div class="lp-body">
      <div><div class="lp-label">顯示</div><span class="chips" id="modeChips"></span></div>
      <div class="lp-toggles"><label><input type="checkbox" id="moveToggle" checked />魚群熱區與漂移</label></div>
      <span id="modeHint" class="note"></span>
      <div class="kpi" id="kpi"></div>
      <div class="legend" id="legend"></div>
      <div id="spPanel" style="display:none;border-top:1px solid #24344f;padding-top:8px;">
        <h3 style="margin:2px 0 6px;" id="spTitle"></h3>
        <div id="spInfo" style="font-size:0.82rem;line-height:1.7;"></div>
        <div id="moveInfo" style="font-size:0.82rem;margin-top:6px;color:#9fd3ff;"></div>
      </div>
      <div style="border-top:1px solid #24344f;padding-top:8px;">
        <h3 id="tblTitle" style="margin:2px 0 6px;">排序（點擊看海溫時序）</h3>
        <div style="max-height:180px;overflow:auto;"><table id="tbl"><thead></thead><tbody></tbody></table></div>
      </div>
      <div style="border-top:1px solid #24344f;padding-top:8px;">
        <h3 id="ct" style="margin:2px 0 6px;">Sea Temperature</h3>
        <div class="chartbox" style="height:160px;"><canvas id="chart"></canvas></div>
      </div>
    </div>
  </div>
  <div class="timebar">
    <button class="tbtn" id="playBtn" title="自動播放" aria-label="自動播放">&#9654;</button>
    <div class="tslider">
      <div class="tlabel" id="tlabel">時間軸</div>
      <input type="range" id="tslider" min="0" max="0" value="0" step="1" />
      <div class="tticks" id="tticks"></div>
    </div>
  </div>
  <div class="floathint">即時浮標海溫與魚種棲地、魚群熱區與漂移；拖曳下方時間軸回放近兩日。完整說明點右上 <b>i</b>。</div>
</div>
__MODAL__
<script>
const DATA = __DATA__;
const SPECIES = __SPECIES__;
const GRID = __GRID__;
const TIMES = __TIMES__;
const COAST = __COAST__;
const MONTH = __MONTH__;
const STEP = __STEP__;
const OVERALL = '__OVERALL__';
const IDW_RADIUS = 120;   // km，與後端一致

function haversineKm(a,b,c,d){const R=6371,p=Math.PI/180;
  const u=Math.sin((c-a)*p/2)**2+Math.cos(a*p)*Math.cos(c*p)*Math.sin((d-b)*p/2)**2;
  return 2*R*Math.asin(Math.sqrt(u));}
// 以各站某時刻 SST，IDW 重算單一網格點（與後端同公式）
function idwSST(lat,lon,vals){let num=0,den=0,near=1e9;
  for(let k=0;k<DATA.length;k++){const v=vals[k]; if(v==null)continue;
    const d=haversineKm(lat,lon,DATA[k].lat,DATA[k].lon);
    if(d<near)near=d; if(d<=IDW_RADIUS){const w=1/(d*d+1);num+=w*v;den+=w;}}
  return (den>0&&near<=IDW_RADIUS)?num/den:null;}

function suit(sst, sp){ if(sst==null)return 0;
  const {sst_min:a,opt_lo:b,opt_hi:c,sst_max:d}=sp; let t;
  if(sst<=a||sst>=d)t=0; else if(sst>=b&&sst<=c)t=1; else if(sst<b)t=(sst-a)/(b-a); else t=(d-sst)/(d-c);
  return Math.round(t*(sp.season.includes(MONTH)?1:0.55)*1000)/10; }
function heat(v){const x=Math.max(0,Math.min(100,v))/100;
  const r=Math.round(46+x*(215-46)),g=Math.round(147-x*(147-38)),b=Math.round(108-x*(108-61));
  return `rgb(${r},${g},${b})`;}
function colorFor(s){return s>=60?'#d7263d':s>=35?'#f0a202':'#2e933c';}
function valFor(s,mode){return mode===OVERALL?s.fish_score:(s.species[mode]??0);}

const map = L.map('map').setView([23.7,121.0],7);
map.zoomControl.setPosition('bottomright');   // 移開左上，避免被左側標題面板遮住
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  {subdomains:'abcd',maxZoom:18,attribution:'© OpenStreetMap © CARTO'}).addTo(map);
const gridRenderer = L.canvas({padding:0.5});  // 網格矩形用 canvas 算繪，效能佳
const gridLayer = L.layerGroup().addTo(map);
const moveLayer = L.layerGroup().addTo(map);
// 陸地畫在高層 pane（zIndex 450）：蓋住網格在岸邊的溢出，且大陸等所有陸地清晰可辨
map.createPane('land'); map.getPane('land').style.zIndex='450';
L.geoJSON(COAST,{pane:'land',interactive:false,
  style:{fillColor:'#26344d',fillOpacity:1,color:'#6f8db3',weight:1}}).addTo(map);
// 浮標與熱點圈畫在陸地之上（zIndex 460），避免沿岸測站被陸地遮住
map.createPane('top'); map.getPane('top').style.zIndex='460';

let curMode = OVERALL;
const modeChips = document.getElementById('modeChips');
function addChip(val,label){const lab=document.createElement('label');lab.dataset.v=val;
  lab.innerHTML=`<input type="radio" name="m" ${val===curMode?'checked':''}/> ${label}`;
  lab.classList.toggle('on',val===curMode);
  lab.querySelector('input').onchange=()=>{curMode=val;
    [...modeChips.children].forEach(c=>c.classList.toggle('on',c.dataset.v===val));render(val);__emitSp();};
  modeChips.appendChild(lab);}
addChip(OVERALL,'綜合潛在漁場');
SPECIES.forEach(sp=>addChip(sp.name,sp.name));
document.getElementById('moveToggle').onchange=()=>render(curMode);

// P1.5 跨時段魚種同步適配器：本頁為單選，套用所收名單中第一個本頁有的魚種(其餘時段的複選在此收斂為單選)
function __applyMode(val){curMode=val;
  [...modeChips.children].forEach(c=>{const on=c.dataset.v===val;c.classList.toggle('on',on);
    const inp=c.querySelector('input');if(inp)inp.checked=on;});render(val);}
window.__getSpecies=()=>curMode===OVERALL?[]:[curMode];
window.__setSpecies=names=>{const nm=(names||[]).find(x=>SPECIES.some(s=>s.name===x));__applyMode(nm||OVERALL);};
window.addEventListener('message',e=>{const d=e.data||{};if(d.nsp==='fishsync'&&d.type==='apply'&&window.__setSpecies)window.__setSpecies(d.names||[]);});
function __emitSp(){try{if(window.parent!==window)parent.postMessage({nsp:'fishsync',type:'changed',names:window.__getSpecies()},'*');}catch(e){}}
try{if(window.parent!==window)parent.postMessage({nsp:'fishsync',type:'ready'},'*');}catch(e){}

function drawGrid(sp){gridLayer.clearLayers(); if(!sp)return;
  GRID.forEach(c=>{const v=suit(c.v,sp); if(v<=0)return;
    L.rectangle([[c.lat-STEP/2,c.lon-STEP/2],[c.lat+STEP/2,c.lon+STEP/2]],
      {stroke:false,fillColor:heat(v),fillOpacity:0.5,renderer:gridRenderer}).addTo(gridLayer);});}

const DIR8=['北','東北','東','東南','南','西南','西','西北'];
function bearingDeg(u,w){return (Math.atan2(u,w)*180/Math.PI+360)%360;}  // 0=北,90=東(順時針)
function dirName(deg){return DIR8[Math.round(deg/45)%8];}

// 魚群熱區：高適合度網格做連通分群（上下左右相鄰即同群），
// 相鄰格聯集成一塊不規則高亮區（沿實際格子邊界），整塊只放一支聚合方向箭頭與標籤，
// 避免密集區出現一串重疊小圈與打架標籤。
const HOT_THR=70;          // 熱區門檻：棲地適合度
const CELL_KM2=28;         // 0.05°×0.05° 海域格約 28 km²（供面積估算）
function gkey(la,lo){return `${Math.round(la/STEP)}|${Math.round(lo/STEP)}`;}
function drawMovement(sp){
  moveLayer.clearLayers();
  if(!sp || !document.getElementById('moveToggle').checked) return;
  // 1. 取高適合度格子，建格座標索引供相鄰判定
  const hot=GRID.map(c=>({c,v:suit(c.v,sp)})).filter(o=>o.v>=HOT_THR);
  if(!hot.length) return;
  const byKey=new Map(); hot.forEach(o=>byKey.set(gkey(o.c.lat,o.c.lon),o));
  // 2. connected-components 分群（4 鄰接）
  const seen=new Set(), clusters=[];
  const NB=[[STEP,0],[-STEP,0],[0,STEP],[0,-STEP]];
  for(const o of hot){
    const k0=gkey(o.c.lat,o.c.lon);
    if(seen.has(k0)) continue;
    const stack=[o], group=[]; seen.add(k0);
    while(stack.length){
      const cur=stack.pop(); group.push(cur);
      for(const [dla,dlo] of NB){
        const nk=gkey(cur.c.lat+dla,cur.c.lon+dlo);
        if(byKey.has(nk) && !seen.has(nk)){ seen.add(nk); stack.push(byKey.get(nk)); }
      }
    }
    clusters.push(group);
  }
  // 3. 每群：聯集填色 + 邊界外框 + 單一聚合方向箭頭與標籤
  const half=STEP/2;
  clusters.forEach(group=>{
    const keys=new Set(group.map(o=>gkey(o.c.lat,o.c.lon)));
    // 3a. 填色矩形（無邊框，相鄰自然連成一片）
    group.forEach(({c})=>{
      L.rectangle([[c.lat-half,c.lon-half],[c.lat+half,c.lon+half]],
        {stroke:false,fillColor:'#ffd000',fillOpacity:0.18,pane:'top',renderer:gridRenderer}).addTo(moveLayer);
    });
    // 3b. 邊界外框：只畫未與同群相鄰的格邊，得到沿實際footprint的單一外框
    group.forEach(({c})=>{
      if(!keys.has(gkey(c.lat+STEP,c.lon))) L.polyline([[c.lat+half,c.lon-half],[c.lat+half,c.lon+half]],{color:'#ffd000',weight:2,opacity:0.9,pane:'top'}).addTo(moveLayer);
      if(!keys.has(gkey(c.lat-STEP,c.lon))) L.polyline([[c.lat-half,c.lon-half],[c.lat-half,c.lon+half]],{color:'#ffd000',weight:2,opacity:0.9,pane:'top'}).addTo(moveLayer);
      if(!keys.has(gkey(c.lat,c.lon+STEP))) L.polyline([[c.lat-half,c.lon+half],[c.lat+half,c.lon+half]],{color:'#ffd000',weight:2,opacity:0.9,pane:'top'}).addTo(moveLayer);
      if(!keys.has(gkey(c.lat,c.lon-STEP))) L.polyline([[c.lat-half,c.lon-half],[c.lat+half,c.lon-half]],{color:'#ffd000',weight:2,opacity:0.9,pane:'top'}).addTo(moveLayer);
    });
    // 3c. 聚合方向（群內各格海流平均）與群質心
    const uv=group.filter(o=>o.c.u!==undefined);
    let mu=0,mw=0; uv.forEach(o=>{mu+=o.c.u;mw+=o.c.w;});
    const hasUv=uv.length>0; if(hasUv){mu/=uv.length;mw/=uv.length;}
    const spd=hasUv?Math.hypot(mu,mw):null;
    const deg=spd!=null?bearingDeg(mu,mw):null;
    const dir=deg!=null?dirName(deg):null;
    const clat=group.reduce((a,o)=>a+o.c.lat,0)/group.length;
    const clon=group.reduce((a,o)=>a+o.c.lon,0)/group.length;
    const vmax=Math.max(...group.map(o=>o.v));
    // 單一標籤 + 工具提示（含涵蓋格數與面積、最高適合度、移動方位）
    L.marker([clat,clon],{pane:'top',icon:L.divIcon({className:'',
      html:`<div class="hotlabel">魚群熱區${dir?'·往'+dir:''}</div>`,
      iconSize:[88,16],iconAnchor:[44,8]})}).addTo(moveLayer)
      .bindTooltip(`魚群熱區 · ${sp.name}`
        +`<br/>涵蓋 ${group.length} 格（約 ${(group.length*CELL_KM2).toFixed(0)} km²）`
        +`<br/>最高棲地適合度 ${vmax.toFixed(1)}／100`
        +(spd!=null?`<br/>可能移動：往${dir}（海流 ${spd.toFixed(2)} m/s）`:'<br/>移動方位：海流資料不足'),
        {direction:'top'});
    // 單一聚合方向箭頭（自群質心畫出，越長流速越大）
    if(spd!=null && spd>0.001){
      const sc=0.9, lat2=clat+mw*sc, lon2=clon+mu*sc;
      L.polyline([[clat,clon],[lat2,lon2]],{color:'#7fd4ff',weight:2.5,opacity:0.95,pane:'top'}).addTo(moveLayer);
      L.marker([lat2,lon2],{pane:'top',icon:L.divIcon({className:'',
        html:`<div class="drift" style="transform:rotate(${deg}deg)"></div>`,
        iconSize:[14,14],iconAnchor:[7,7]})}).addTo(moveLayer);
    }
  });
}

let markers=[], chart;
function render(mode){
  markers.forEach(m=>map.removeLayer(m)); markers=[];
  const sp0=SPECIES.find(x=>x.name===mode); drawGrid(sp0); drawMovement(sp0);
  const rows=DATA.map(s=>({s,v:valFor(s,mode)})).sort((a,b)=>b.v-a.v);
  rows.forEach(({s,v})=>{const m=L.circleMarker([s.lat,s.lon],
    {pane:'top',radius:5+v/12,color:'#fff',weight:1.2,fillColor:colorFor(v),fillOpacity:0.95}).addTo(map);
    m.bindTooltip(`${s.name}<br/>座標 ${s.lat.toFixed(3)}, ${s.lon.toFixed(3)}<br/>SST=${s.sst}°C 流速=${s.current??'-'}<br/>${mode===OVERALL?'漁場指標':mode}=${v}`);
    m.on('click',()=>showChart(s)); markers.push(m);});

  const vals=rows.map(r=>r.v), hi=vals.filter(v=>v>=60).length;
  document.getElementById('kpi').innerHTML=`
    <div>有效浮標<b>${DATA.length}</b></div>
    <div>高分站(≥60)<b style="color:#d7263d">${hi}</b></div>
    <div>SST範圍<b>${Math.min(...DATA.map(s=>s.sst)).toFixed(1)}–${Math.max(...DATA.map(s=>s.sst)).toFixed(1)}</b></div>
    <div>最高分<b style="color:${colorFor(vals[0])}">${vals[0]}</b></div>`;
  document.getElementById('legend').innerHTML = mode===OVERALL
    ? '潛在漁場指標：<span style="background:#2e933c"></span>低<span style="background:#f0a202"></span>中<span style="background:#d7263d"></span>高'
    : '棲地適合度：<span class="bar"></span>低 → 高'
      + '　<span class="lg-zone"></span>魚群熱區'
      + '　<span class="lg-arrow"></span>可能移動方位（海流）';

  const sp=sp0, spPanel=document.getElementById('spPanel');
  if(sp){spPanel.style.display='';
    document.getElementById('spTitle').textContent=`${sp.name}（${sp.en}） ${sp.sci}`;
    const inS=sp.season.includes(MONTH);
    document.getElementById('spInfo').innerHTML=`
      <div>適溫窗：<b style="color:#ffd166">${sp.opt_lo}–${sp.opt_hi}°C</b>（容忍 ${sp.sst_min}–${sp.sst_max}°C）</div>
      <div>盛漁期：${sp.season.join('、')} 月　本月：<b style="color:${inS?'#2e933c':'#f0a202'}">${inS?'盛漁期':'非盛漁期'}</b></div>
      <div>主要漁場：${sp.region}　水層：${sp.depth}</div>
      <div style="margin-top:4px;">習性：${sp.habit}</div>`;
    // 棲地移動趨勢（平均 SST 趨勢 + 平均流向）
    const trs=GRID.filter(c=>c.tr!==undefined).map(c=>c.tr);
    const avgTr=trs.length?trs.reduce((a,b)=>a+b,0)/trs.length:0;
    let dirTxt='海流資料不足';
    const us=GRID.filter(c=>c.u!==undefined);
    if(us.length){const mu=us.reduce((a,c)=>a+c.u,0)/us.length, mw=us.reduce((a,c)=>a+c.w,0)/us.length;
      const sp2=Math.hypot(mu,mw); const dir=(Math.atan2(mu,mw)*180/Math.PI+360)%360;
      const names=['北','東北','東','東南','南','西南','西','西北'];
      dirTxt=`平均流向 ${names[Math.round(dir/45)%8]}（${sp2.toFixed(2)} m/s）`;}
    const warm=(sp.opt_lo+sp.opt_hi)/2>=23;
    const shift=avgTr>0.02?(warm?'升溫→暖水適宜帶向北/外擴':'升溫→冷水適宜帶收縮北退')
      :avgTr<-0.02?(warm?'降溫→暖水適宜帶南縮':'降溫→冷水適宜帶南擴'):'海溫穩定，棲地短期內變動小';
    document.getElementById('moveInfo').innerHTML=
      `移動研判：${dirTxt}；近6小時海溫趨勢 ${avgTr>0?'+':''}${avgTr.toFixed(3)}°C/hr → ${shift}`;
    document.getElementById('modeHint').textContent=`連續內插「${sp.name}」棲地適合度，金色高亮為魚群熱區、藍色箭頭為可能移動方位`;
  }else{spPanel.style.display='none';
    document.getElementById('modeHint').textContent='海洋鋒面與海流綜合之潛在漁場熱區';}

  const isSp=mode!==OVERALL;
  document.querySelector('#tbl thead').innerHTML=isSp
    ?'<tr><th>站名</th><th>緯度,經度</th><th>SST(°C)</th><th>適合度</th></tr>'
    :'<tr><th>站名</th><th>緯度,經度</th><th>SST(°C)</th><th>鋒面</th><th>流速</th><th>指標</th></tr>';
  const tb=document.querySelector('#tbl tbody'); tb.innerHTML='';
  rows.forEach(({s,v})=>{const tr=document.createElement('tr');
    const xy=`${s.lat.toFixed(2)},${s.lon.toFixed(2)}`;
    tr.innerHTML=isSp
      ?`<td>${s.name}</td><td>${xy}</td><td>${s.sst}</td><td><span class="badge" style="background:${colorFor(v)}">${v}</span></td>`
      :`<td>${s.name}</td><td>${xy}</td><td>${s.sst}</td><td>${s.front}</td><td>${s.current??'-'}</td><td><span class="badge" style="background:${colorFor(v)}">${v} ${s.level}</span></td>`;
    tr.onclick=()=>{showChart(s);map.setView([s.lat,s.lon],9);}; tb.appendChild(tr);});
  document.getElementById('tblTitle').textContent=(isSp?`${mode} 適合度排序`:'潛在漁場排序')+'（點擊看海溫時序）';
}

function showChart(s){
  document.getElementById('ct').textContent=`${s.name} — Sea Temperature (last 2 days)`;
  const labels=s.sst_series.map(p=>p.t.slice(5,16).replace('T',' ')), v=s.sst_series.map(p=>p.v);
  if(chart)chart.destroy();
  chart=new Chart(document.getElementById('chart'),{type:'line',
    data:{labels,datasets:[{label:'Sea Temperature (°C)',data:v,borderColor:'#ff7043',
      backgroundColor:'rgba(255,112,67,.15)',fill:true,tension:.3,borderWidth:2,
      pointRadius:3.5,pointHoverRadius:6,pointBackgroundColor:'#ff7043'}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#cdd9e5'}}},
      scales:{x:{ticks:{color:'#8aa0b8',maxTicksLimit:8},grid:{color:'#1c2c46'}},
        y:{title:{display:true,text:'SST (°C)',color:'#ff7043'},ticks:{color:'#8aa0b8'},grid:{color:'#1c2c46'}}}}});
}

// 點地圖空白處：顯示該點經緯度與最近網格的海況資訊
map.on('click',e=>{
  const lat=e.latlng.lat, lon=e.latlng.lng;
  let best=null,bd=1e9;
  GRID.forEach(c=>{const d=Math.hypot(c.lat-lat,c.lon-lon); if(d<bd){bd=d;best=c;}});
  let html=`座標 ${lat.toFixed(3)}, ${lon.toFixed(3)}`;
  if(best && bd<=STEP*1.5){
    html+=`<br/>SST ${best.v}°C`;
    const sp=SPECIES.find(x=>x.name===curMode);
    html+= sp?`<br/>${sp.name} 棲地適合度 ${suit(best.v,sp)}／100`:'<br/>（綜合潛在漁場模式）';
    if(best.u!==undefined)
      html+=`<br/>海流 ${Math.hypot(best.u,best.w).toFixed(2)} m/s 往${dirName(bearingDeg(best.u,best.w))}`;
  }else{
    html+='<br/>此處不在浮標有效內插範圍（最近浮標逾 120km）';
  }
  L.popup().setLatLng(e.latlng).setContent(html).openOn(map);
});

render(OVERALL);
showChart(DATA[0]);

// 時間軸：拖曳以該時刻各站 SST 重算海溫場與棲地熱區（可拖曳 + 播放，近兩日逐時回放）
const tslider=document.getElementById('tslider'), tlabel=document.getElementById('tlabel');
function setTime(i){
  const vals=DATA.map(s=>s.sst_t?s.sst_t[i]:null);
  GRID.forEach(c=>{const v=idwSST(c.lat,c.lon,vals); c.v=(v==null?null:Math.round(v*100)/100);});
  render(curMode);
  tlabel.textContent=(TIMES[i]||'').slice(5,16).replace('T',' ');
}
if(TIMES.length){tslider.max=TIMES.length-1; tslider.value=TIMES.length-1;
  tslider.oninput=()=>setTime(+tslider.value);
  // 起訖刻度
  const tk=document.getElementById('tticks');
  tk.innerHTML=`<span>${(TIMES[0]||'').slice(5,10)}</span><span>${(TIMES[TIMES.length-1]||'').slice(5,10)}</span>`;
  setTime(TIMES.length-1);
  let pT=null;const pB=document.getElementById('playBtn');
  pB.onclick=function(){if(pT){clearInterval(pT);pT=null;pB.innerHTML='&#9654;';return;}
    pB.innerHTML='&#10074;&#10074;';pT=setInterval(()=>{let n=(+tslider.value+1)%TIMES.length;tslider.value=n;setTime(n);},900);};
}
// 右側面板收合(點標題列；點 i 不收合) + 左側標題面板收合/重開 + 地圖尺寸校正
document.getElementById('lpHead').onclick=function(e){if(e.target.closest('#infoBtn'))return;
  document.getElementById('layerPanel').classList.toggle('collapsed');};
var lP=document.getElementById('leftPanel'),lR=document.getElementById('leftReopen');
document.getElementById('leftCollapse').onclick=function(){lP.style.display='none';lR.style.display='flex';};
lR.onclick=function(){lP.style.display='';lR.style.display='none';};
setTimeout(function(){map.invalidateSize();},150);
window.addEventListener('resize',function(){map.invalidateSize();});
__MODALJS__
</script>
</body></html>
"""

if __name__ == "__main__":
    build()
