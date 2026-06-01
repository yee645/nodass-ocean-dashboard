"""題目 0：NODASS 開放浮標 → 漁場環境 + 經濟魚種棲地預測（連續、即時、含移動）。

精確範圍：以 0.05° 細網格 IDW 內插 SST，逐網格算魚種棲地適合度（canvas 算繪）。
即時更新：執行 live_update.py（可搭排程）重抓最新浮標資料重建，使用者重整頁面即見最新。
魚群位置與移動：
  - 魚群熱點 = 適合度高的網格（局部極大）。
  - 漂移方向 = 浮標實測表層海流向量內插（魚群隨流移動）。
  - 棲地趨勢 = 近 6 小時 SST 變化（升/降溫 → 暖/冷水魚種棲地擴張或收縮）。
魚種習性見 species_traits.py。完整葉綠素/歷史需會員管制資料權限。
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

from dashboard_common import (SHARED_CSS, haversine, load_coast, nav_html,
                              on_land)
from species_traits import SPECIES, suitability

DATA_DIR = Path(r"D:\nodass")
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
    lat = 21.5
    while lat <= 26.6:
        lon = 119.0
        while lon <= 122.6:
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

    sst_st.sort(key=lambda s: s["fish_score"], reverse=True)

    sst_pts = [(s["lat"], s["lon"], s["sst"]) for s in sst_st]
    u_pts = [(s["lat"], s["lon"], s["u"]) for s in stations if s.get("u") is not None]
    v_pts = [(s["lat"], s["lon"], s["w"]) for s in stations if s.get("w") is not None]
    tr_pts = [(s["lat"], s["lon"], s["trend"]) for s in stations if s.get("trend") is not None]
    grid = build_combined_grid(sst_pts, u_pts, v_pts, tr_pts)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = (TPL.replace("__CSS__", SHARED_CSS)
               .replace("__NAV__", nav_html("fish"))
               .replace("__DATA__", json.dumps(sst_st, ensure_ascii=False))
               .replace("__SPECIES__", json.dumps(SPECIES, ensure_ascii=False))
               .replace("__GRID__", json.dumps(grid, ensure_ascii=False))
               .replace("__COAST__", load_coast())
               .replace("__MONTH__", str(month))
               .replace("__STEP__", str(GRID_STEP))
               .replace("__TS__", generated))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    print(f"已產生 {OUT}  有效站數={len(sst_st)}  魚種={len(SPECIES)}  "
          f"細網格={len(grid)}(step={GRID_STEP}°)  海流站={len(u_pts)}  月份={month}")


TPL = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NODASS 漁場環境與經濟魚種棲地預測</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>__CSS__
  /* 魚群熱點：金色圓標內含「魚」字，醒目且與浮標圓點明顯區隔 */
  .fishhot{width:22px;height:22px;line-height:20px;text-align:center;border-radius:50%;
    background:#ffb300;color:#3a2600;font-weight:700;font-size:12px;border:2px solid #fff;
    box-shadow:0 0 6px rgba(0,0,0,.6);}
  /* 海流漂移箭頭：向上三角形，依流向旋轉 */
  .drift{width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;
    border-bottom:12px solid #7fd4ff;filter:drop-shadow(0 0 2px #000);}
  /* 圖例樣本（class 選擇器特異度高於共用樣式的 .legend span，可覆寫尺寸） */
  .legend .bar{width:80px;height:10px;border-radius:3px;
    background:linear-gradient(90deg,rgb(46,147,108),rgb(240,162,2),rgb(215,38,61));}
  .legend .lg-fish{width:16px;height:16px;line-height:14px;text-align:center;border-radius:50%;
    background:#ffb300;color:#3a2600;font-weight:700;font-size:10px;border:1.5px solid #fff;}
  .legend .lg-arrow{width:0;height:0;border-radius:0;border-left:5px solid transparent;
    border-right:5px solid transparent;border-bottom:11px solid #7fd4ff;}
</style>
</head>
<body>
<header>
  <h1>NODASS 漁場環境與經濟魚種棲地預測儀表板</h1>
  <div class="sub">海溫鋒面 × 海流 × 魚種適溫窗 ｜ 連續內插 0.05° ｜ 資料來源：NODASS 開放浮標 API ｜ 產生 __TS__（第 __MONTH__ 月）</div>
</header>
__NAV__
<div class="ctrl">
  <label for="mode">顯示模式：</label>
  <select id="mode"><option value="__OVERALL__">綜合潛在漁場指標</option></select>
  <label><input type="checkbox" id="moveToggle" checked />顯示魚群熱點與漂移方向</label>
  <span id="modeHint" class="note"></span>
</div>
<div class="wrap">
  <div id="map"></div>
  <div class="side">
    <div class="panel">
      <div class="kpi" id="kpi"></div>
      <div class="legend" style="margin-top:8px;" id="legend"></div>
    </div>
    <div class="panel" id="spPanel" style="display:none;">
      <h3 style="margin:4px 0 8px;" id="spTitle"></h3>
      <div id="spInfo" style="font-size:0.82rem;line-height:1.7;"></div>
      <div id="moveInfo" style="font-size:0.82rem;margin-top:6px;color:#9fd3ff;"></div>
    </div>
    <div class="panel">
      <h3 id="tblTitle" style="margin:4px 0 8px;">排序（點擊看海溫時序）</h3>
      <div style="max-height:200px;overflow:auto;">
        <table id="tbl"><thead></thead><tbody></tbody></table>
      </div>
    </div>
    <div class="panel">
      <h3 id="ct" style="margin:4px 0 8px;">Sea Temperature</h3>
      <div class="chartbox"><canvas id="chart"></canvas></div>
    </div>
  </div>
</div>
<div class="wrap"><div class="panel" style="flex:1;"><div class="note">
  <b>魚種棲地適合度（0–100）</b>：適溫窗梯形隸屬函數 × 季節因子，將浮標 SST 以 IDW 內插成 0.05° 連續海域網格；色塊邊界已用精細海岸線遮罩，僅顯示海域、不溢出陸地。<br/>
  <b>魚群熱點（金色「魚」標）</b>：在適合度 ≥70 的海域網格中，依適合度高低並維持最小間距（約 35km）挑出最多 10 處代表性熱區，避免整片標記。<b>漂移方向（藍色箭頭）</b>：該處浮標實測表層海流向量內插，代表魚群可能隨流移動的去向，箭頭越長流速越大。<br/>
  <b>棲地趨勢</b>：近 6 小時 SST 變化；升溫使暖水魚種適宜帶向北/外擴、冷水魚種收縮，反之亦然。<br/>
  <b>無色塊區域</b>：代表該海域不在開放浮標的有效內插範圍（最近浮標逾 120km），本系統不外推，以維持結果可信。<br/>
  <b>即時</b>：執行 live_update.py（可搭排程）重抓最新浮標資料並重建，重整頁面即見最新。完整葉綠素/歷史需會員權限。對齊 SDG 14。
</div></div></div>
<script>
const DATA = __DATA__;
const SPECIES = __SPECIES__;
const GRID = __GRID__;
const COAST = __COAST__;
const MONTH = __MONTH__;
const STEP = __STEP__;
const OVERALL = '__OVERALL__';

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
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  {subdomains:'abcd',maxZoom:18,attribution:'© OpenStreetMap © CARTO'}).addTo(map);
// 內嵌海岸線：無底圖（如 file://）時仍顯示陸地與地理範圍
L.geoJSON(COAST,{style:{fillColor:'#1b2a3a',fillOpacity:1,color:'#46627f',weight:1}}).addTo(map);
const gridRenderer = L.canvas({padding:0.5});  // 網格矩形用 canvas 算繪，效能佳且不影響底圖
const gridLayer = L.layerGroup().addTo(map);
const moveLayer = L.layerGroup().addTo(map);

const sel = document.getElementById('mode');
SPECIES.forEach(sp=>{const o=document.createElement('option');o.value=sp.name;
  o.textContent=`魚種：${sp.name}（${sp.en}）`;sel.appendChild(o);});
sel.onchange=()=>render(sel.value);
document.getElementById('moveToggle').onchange=()=>render(sel.value);

function drawGrid(sp){gridLayer.clearLayers(); if(!sp)return;
  GRID.forEach(c=>{const v=suit(c.v,sp); if(v<=0)return;
    L.rectangle([[c.lat-STEP/2,c.lon-STEP/2],[c.lat+STEP/2,c.lon+STEP/2]],
      {stroke:false,fillColor:heat(v),fillOpacity:0.5,renderer:gridRenderer}).addTo(gridLayer);});}

const DIR8=['北','東北','東','東南','南','西南','西','西北'];
function bearingDeg(u,w){return (Math.atan2(u,w)*180/Math.PI+360)%360;}  // 0=北,90=東(順時針)
function dirName(deg){return DIR8[Math.round(deg/45)%8];}

// 魚群熱點：在高適合度網格中以最小間距去叢集，挑出少數分散的代表性熱區，
// 避免整片標記；每處再以實測海流向量畫出漂移方向箭頭。
function drawMovement(sp){
  moveLayer.clearLayers();
  if(!sp || !document.getElementById('moveToggle').checked) return;
  const scored=GRID.map(c=>({c,v:suit(c.v,sp)})).filter(o=>o.v>=70).sort((a,b)=>b.v-a.v);
  const MIN_SEP=0.35;      // 熱點最小間距（度，約 35km）
  const MAX_HOT=10;        // 最多熱點數
  const picked=[];
  for(const o of scored){
    if(picked.length>=MAX_HOT) break;
    if(picked.every(p=>Math.hypot(p.c.lat-o.c.lat,p.c.lon-o.c.lon)>=MIN_SEP)) picked.push(o);
  }
  const hotIcon=L.divIcon({className:'',html:'<div class="fishhot">魚</div>',
    iconSize:[22,22],iconAnchor:[11,11]});
  picked.forEach(({c,v})=>{
    const spd=(c.u!==undefined)?Math.hypot(c.u,c.w):null;
    L.marker([c.lat,c.lon],{icon:hotIcon}).bindTooltip(
      `魚群熱點 · ${sp.name}<br/>座標 ${c.lat.toFixed(3)}, ${c.lon.toFixed(3)}`
      +`<br/>棲地適合度 ${v}／100　SST ${c.v}°C`
      +(spd!=null?`<br/>海流漂移 ${spd.toFixed(2)} m/s（往${dirName(bearingDeg(c.u,c.w))}）`:''),
      {direction:'top'}).addTo(moveLayer);
    if(spd!=null && spd>0.001){
      const sc=0.9;                                   // 流速→經緯度長度縮放
      const lat2=c.lat+c.w*sc, lon2=c.lon+c.u*sc;
      L.polyline([[c.lat,c.lon],[lat2,lon2]],{color:'#7fd4ff',weight:2.5,opacity:0.95}).addTo(moveLayer);
      const deg=bearingDeg(c.u,c.w);
      L.marker([lat2,lon2],{icon:L.divIcon({className:'',
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
    {radius:5+v/12,color:'#fff',weight:1.2,fillColor:colorFor(v),fillOpacity:0.95}).addTo(map);
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
      + '　<span class="lg-fish">魚</span>魚群熱點'
      + '　<span class="lg-arrow"></span>海流漂移方向';

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
    document.getElementById('modeHint').textContent=`連續內插「${sp.name}」棲地適合度，金色「魚」標為魚群熱點、藍色箭頭為海流漂移方向`;
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

render(OVERALL);
showChart(DATA[0]);
</script>
</body></html>
"""

if __name__ == "__main__":
    build()
