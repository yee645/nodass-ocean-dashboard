"""由 NODASS 浮標近兩日資料計算極端浪況風險，產生獨立 HTML 儀表板（題目 3）。

- 資料來源：NODASS 開放浮標 API（無需授權），全台 26 座浮標逐時資料。
- 風險指標透明可解釋，不依賴開放視窗中缺漏的最大波高欄位。
- 連續波高熱區：以 IDW 將浮標示性波高內插成海域網格，提供整片海域的直觀範圍。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dashboard_common import (INFO_MODAL_JS, SHARED_CSS, build_grid, info_modal,
                              load_coast, nav_html)

DATA_DIR = Path(__file__).resolve().parent      # 專案根(相對於本檔)，取代舊硬編絕對路徑
SRC = DATA_DIR / "buoy_window.json"
OUT_DIR = DATA_DIR / "dashboard"
OUT = OUT_DIR / "index.html"

# 風險權重（總分 0~100）
W_HS, W_SURGE, W_SWELL, W_GUST, W_PRES = 40.0, 25.0, 15.0, 10.0, 10.0
HS_CAP, SURGE_CAP, PRES_DROP_CAP = 4.0, 0.5, 3.0


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def coalesce_period(rec: dict) -> float | None:
    for key in ("Wave_Peak_Period", "Wave_Period_Significant", "Wave_Mean_Period"):
        v = rec.get(key)
        if v is not None:
            return v
    return None


def series(recs: list[dict], field: str) -> list[tuple[str, float]]:
    out = []
    for r in recs:
        v = r.get(field)
        t = r.get("DateTime") or r.get("time")
        if v is not None and t is not None:
            out.append((t, float(v)))
    return out


def compute_station(obj: dict) -> dict:
    recs = sorted(obj["records"], key=lambda r: r.get("time") or "")
    hs = series(recs, "Wave_Height_Significant")
    per = []
    for r in recs:
        p = coalesce_period(r)
        t = r.get("DateTime") or r.get("time")
        if p is not None and t is not None:
            per.append((t, float(p)))

    hs_now = hs[-1][1] if hs else None
    period_now = per[-1][1] if per else None

    surge = 0.0
    vals = [v for _, v in hs]
    for i in range(max(1, len(vals) - 3), len(vals)):
        surge = max(surge, vals[i] - vals[i - 1])

    swell = 1.0 if (period_now is not None and period_now >= 8.0
                    and hs_now is not None and hs_now >= 1.5) else 0.0

    gust_factor = 0.0
    gusts = series(recs, "Wind_Gust_Speed")
    winds = series(recs, "Wind_Speed")
    if gusts and winds and winds[-1][1] > 0.5:
        gust_factor = gusts[-1][1] / winds[-1][1]

    pres = [v for _, v in series(recs, "Air_Pressure")]
    pres_drop = pres[-4] - pres[-1] if len(pres) >= 4 else 0.0

    risk = 0.0
    if hs_now is not None:
        risk += W_HS * clamp01(hs_now / HS_CAP)
    risk += W_SURGE * clamp01(surge / SURGE_CAP)
    risk += W_SWELL * swell
    risk += W_GUST * clamp01((gust_factor - 1.0) / 0.5) if gust_factor else 0.0
    risk += W_PRES * clamp01(pres_drop / PRES_DROP_CAP)
    risk = round(min(100.0, risk), 1)

    if risk >= 75:
        level, color = "危險", "#d7263d"
    elif risk >= 50:
        level, color = "警戒", "#f46036"
    elif risk >= 25:
        level, color = "注意", "#f0a202"
    else:
        level, color = "低", "#2e933c"

    return {
        "meta": obj["meta"], "hs_now": hs_now, "period_now": period_now,
        "surge": round(surge, 2), "swell": swell,
        "gust_factor": round(gust_factor, 2) if gust_factor else None,
        "pres_drop": round(pres_drop, 2), "risk": risk, "level": level, "color": color,
        "hs_series": [{"t": t, "v": v} for t, v in hs],
        "period_series": [{"t": t, "v": v} for t, v in per],
    }


def build() -> None:
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    stations = [compute_station(o) for o in raw.values()]
    stations = [s for s in stations if s["hs_now"] is not None]
    stations.sort(key=lambda s: s["risk"], reverse=True)

    grid = build_grid([(s["meta"]["lat"], s["meta"]["lon"], s["hs_now"])
                       for s in stations])

    # 時間軸：對齊各站示性波高時序（前向填補），供前端逐時重算波高熱區
    times = sorted({p["t"] for s in stations for p in s["hs_series"]})
    for s in stations:
        mp = {p["t"]: p["v"] for p in s["hs_series"]}
        last = None; arr = []
        for t in times:
            if t in mp:
                last = mp[t]
            arr.append(last)
        s["hs_t"] = arr

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    OUT_DIR.mkdir(exist_ok=True)
    html = (TPL.replace("__CSS__", SHARED_CSS)
               .replace("__NAV__", nav_html("wave"))
               .replace("__MODAL__", info_modal("關於本頁與資料說明", WAVE_MODAL_BODY))
               .replace("__MODALJS__", INFO_MODAL_JS)
               .replace("__DATA__", json.dumps(stations, ensure_ascii=False))
               .replace("__GRID__", json.dumps(grid, ensure_ascii=False))
               .replace("__TIMES__", json.dumps(times, ensure_ascii=False))
               .replace("__COAST__", load_coast())
               .replace("__TS__", generated))
    OUT.write_text(html, encoding="utf-8")
    top = stations[0]
    print(f"已產生 {OUT}  站數={len(stations)}  網格={len(grid)}")
    print(f"風險最高：{top['meta']['StationNameLocal']} risk={top['risk']} "
          f"({top['level']}) Hs={top['hs_now']}m")


WAVE_MODAL_BODY = """
  <div class="note">
  <b>風險指標（透明可解釋，0–100）</b>：示性波高 40% ＋ 波高暴增率 25%（瘋狗浪前兆）＋ 長週期湧浪旗標 15% ＋ 陣風因子 10% ＋ 3 小時氣壓驟降 10%。<br/><br/>
  <b>連續波高熱區</b>：以反距離加權將 26 浮標示性波高內插成海域網格，僅顯示浮標 120km 內、非陸地之網格。<br/>
  <b>升級路徑</b>：取得 NODASS 管制資料權限後可串接歷史資料訓練 LSTM 做 1–2 小時前異常巨浪機率預測。對齊 SDG 3、14。<br/><br/>
  <b>出海安全</b>正式以中央氣象署海象/漁業氣象與海巡署警報為準，本頁為參考用途。
  </div>
"""


TPL = r"""<!DOCTYPE html>
<html lang="zh-Hant" class="cwa">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NODASS 全台浮標極端浪況即時預警</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>__CSS__</style>
<script>if(window.top!==window.self)document.documentElement.classList.add('embedded');</script>
</head>
<body>
<button class="panel-reopen" id="leftReopen" title="開啟資訊" aria-label="開啟資訊">&#9776;</button>
<div class="leftpanel" id="leftPanel">
  <div class="lpane-head">
    <div class="lpane-title">NODASS 全台浮標極端浪況即時預警</div>
    <button class="lpane-x" id="leftCollapse" title="收合" aria-label="收合">&times;</button>
  </div>
  <div class="lpane-sub">國家海洋資料庫及共享平臺（NODASS）開放浮標 API｜逐時資料近兩日｜產生 __TS__</div>
  __NAV__
</div>
<div class="stage">
  <div id="map"></div>
  <div class="layerpanel" id="layerPanel">
    <div class="lp-head" id="lpHead">
      <h2>圖層</h2>
      <button class="infobtn" id="infoBtn" title="說明" aria-label="說明">i</button>
      <span class="lp-arrow">&#9662;</span>
    </div>
    <div class="lp-body">
      <div class="lp-toggles"><label><input type="checkbox" id="gridToggle" checked />連續波高熱區（IDW）</label></div>
      <span class="note" id="gridLegend"></span>
      <div class="kpi" id="kpi"></div>
      <div class="legend">風險等級：
        <span style="background:#2e933c"></span>低<span style="background:#f0a202"></span>注意
        <span style="background:#f46036"></span>警戒<span style="background:#d7263d"></span>危險</div>
      <div style="border-top:1px solid #24344f;padding-top:8px;">
        <h3 style="margin:2px 0 6px;">風險排序（點擊查看時序）</h3>
        <div style="max-height:180px;overflow:auto;">
          <table id="tbl"><thead><tr>
            <th>站名</th><th>緯度,經度</th><th>Hs(m)</th><th>週期(s)</th><th>暴增</th><th>風險</th>
          </tr></thead><tbody></tbody></table>
        </div>
      </div>
      <div style="border-top:1px solid #24344f;padding-top:8px;">
        <h3 id="chartTitle" style="margin:2px 0 6px;">波高時序</h3>
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
  <div class="floathint">全台浮標波高風險與熱區；拖曳下方時間軸回放近兩日。完整指標說明點右上 <b>i</b>。</div>
</div>
__MODAL__
<script>
const DATA = __DATA__;
const GRID = __GRID__;
const TIMES = __TIMES__;
const COAST = __COAST__;
const GRID_STEP = 0.1;
const IDW_RADIUS = 120;   // km，與後端一致

function haversine(a,b,c,d){const R=6371,p=Math.PI/180;
  const u=Math.sin((c-a)*p/2)**2+Math.cos(a*p)*Math.cos(c*p)*Math.sin((d-b)*p/2)**2;
  return 2*R*Math.asin(Math.sqrt(u));}
// 以各站某時刻數值，IDW 重算單一網格點（與後端同公式）
function idwAt(lat,lon,vals){let num=0,den=0,near=1e9;
  for(let k=0;k<DATA.length;k++){const v=vals[k]; if(v==null)continue;
    const d=haversine(lat,lon,DATA[k].meta.lat,DATA[k].meta.lon);
    if(d<near)near=d; if(d<=IDW_RADIUS){const w=1/(d*d+1);num+=w*v;den+=w;}}
  return (den>0&&near<=IDW_RADIUS)?num/den:null;}

const map = L.map('map').setView([23.7, 121.0], 7);
map.zoomControl.setPosition('bottomright');   // 移開左上，避免被左側標題面板遮住
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  { subdomains: 'abcd', maxZoom: 18, attribution: '© OpenStreetMap © CARTO' }).addTo(map);
// 陸地畫在高層 pane（zIndex 450）：蓋住熱區在岸邊的溢出，且大陸等所有陸地清晰可辨
map.createPane('land'); map.getPane('land').style.zIndex = '450';
L.geoJSON(COAST, { pane: 'land', interactive: false,
  style: { fillColor: '#26344d', fillOpacity: 1, color: '#6f8db3', weight: 1 } }).addTo(map);
// 浮標畫在陸地之上（zIndex 460），避免沿岸測站被陸地遮住
map.createPane('top'); map.getPane('top').style.zIndex = '460';

// 波高連續色階（0→4m：綠→黃→紅）
function hsColor(v){const x=Math.max(0,Math.min(4,v))/4;
  const r=Math.round(46+x*(215-46)),g=Math.round(147-x*(147-38)),b=Math.round(108-x*(108-61));
  return `rgb(${r},${g},${b})`;}
const gridRenderer = L.canvas({padding:0.5});
const gridLayer = L.layerGroup().addTo(map);
function drawGrid(){gridLayer.clearLayers();
  if(!document.getElementById('gridToggle').checked)return;
  GRID.forEach(c=>{if(c.v==null)return;
    L.rectangle([[c.lat-GRID_STEP/2,c.lon-GRID_STEP/2],[c.lat+GRID_STEP/2,c.lon+GRID_STEP/2]],
    {stroke:false,fillColor:hsColor(c.v),fillOpacity:0.45,renderer:gridRenderer}).addTo(gridLayer);});}
document.getElementById('gridToggle').onchange=drawGrid;
document.getElementById('gridLegend').innerHTML=
  '波高(m)：<span style="display:inline-block;width:90px;height:10px;vertical-align:middle;'+
  'background:linear-gradient(90deg,rgb(46,147,108),rgb(215,38,61));border-radius:3px;"></span> 0 → 4+';

// 時間軸：拖曳 slider 以該時刻各站波高 IDW 重算熱區
const tslider=document.getElementById('tslider'), tlabel=document.getElementById('tlabel');
function redrawAt(i){
  const vals=DATA.map(s=>s.hs_t?s.hs_t[i]:null);
  GRID.forEach(c=>{c.v=idwAt(c.lat,c.lon,vals);});
  drawGrid();
  tlabel.textContent=(TIMES[i]||'').slice(5,16).replace('T',' ');
}
if(TIMES.length){tslider.max=TIMES.length-1; tslider.value=TIMES.length-1;
  tslider.oninput=()=>redrawAt(+tslider.value); redrawAt(TIMES.length-1);
  const tk=document.getElementById('tticks');
  tk.innerHTML=`<span>${(TIMES[0]||'').slice(5,10)}</span><span>${(TIMES[TIMES.length-1]||'').slice(5,10)}</span>`;
  let pT=null;const pB=document.getElementById('playBtn');
  pB.onclick=function(){if(pT){clearInterval(pT);pT=null;pB.innerHTML='&#9654;';return;}
    pB.innerHTML='&#10074;&#10074;';pT=setInterval(()=>{let n=(+tslider.value+1)%TIMES.length;tslider.value=n;redrawAt(n);},900);};}
else drawGrid();
// 右側面板收合(點 i 不收合) + 左側標題面板收合/重開 + 地圖尺寸校正
document.getElementById('lpHead').onclick=function(e){if(e.target.closest('#infoBtn'))return;
  document.getElementById('layerPanel').classList.toggle('collapsed');};
var lP=document.getElementById('leftPanel'),lR=document.getElementById('leftReopen');
document.getElementById('leftCollapse').onclick=function(){lP.style.display='none';lR.style.display='flex';};
lR.onclick=function(){lP.style.display='';lR.style.display='none';};
setTimeout(function(){map.invalidateSize();},150);
window.addEventListener('resize',function(){map.invalidateSize();});
__MODALJS__

const markers = {};
DATA.forEach(s => {
  const m = L.circleMarker([s.meta.lat, s.meta.lon], {
    pane: 'top', radius: 6 + s.risk / 10, color: '#fff', weight: 1.2, fillColor: s.color, fillOpacity: 0.95
  }).addTo(map);
  m.bindTooltip(`${s.meta.StationNameLocal}<br/>座標 ${s.meta.lat.toFixed(3)}, ${s.meta.lon.toFixed(3)}<br/>Hs=${s.hs_now}m 風險=${s.risk}(${s.level})`);
  m.on('click', () => showChart(s));
  markers[s.meta.StationID] = m;
});

const danger = DATA.filter(s => s.risk >= 50).length;
const maxHs = Math.max(...DATA.map(s => s.hs_now));
document.getElementById('kpi').innerHTML = `
  <div>監測浮標<b>${DATA.length}</b></div>
  <div>警戒以上<b style="color:#f46036">${danger}</b></div>
  <div>最大Hs(m)<b>${maxHs.toFixed(1)}</b></div>
  <div>最高風險<b style="color:${DATA[0].color}">${DATA[0].risk}</b></div>`;

const tb = document.querySelector('#tbl tbody');
DATA.forEach(s => {
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${s.meta.StationNameLocal}</td><td>${s.meta.lat.toFixed(2)},${s.meta.lon.toFixed(2)}</td>
    <td>${s.hs_now}</td><td>${s.period_now ?? '-'}</td><td>${s.surge}</td>
    <td><span class="badge" style="background:${s.color}">${s.risk} ${s.level}</span></td>`;
  tr.onclick = () => { showChart(s); map.setView([s.meta.lat, s.meta.lon], 9); };
  tb.appendChild(tr);
});

// 點地圖空白處：顯示該點經緯度與最近網格內插波高
map.on('click', e => {
  const lat = e.latlng.lat, lon = e.latlng.lng;
  let best = null, bd = 1e9;
  GRID.forEach(c => { const d = Math.hypot(c.lat - lat, c.lon - lon); if (d < bd) { bd = d; best = c; } });
  let html = `座標 ${lat.toFixed(3)}, ${lon.toFixed(3)}`;
  html += (best && bd <= GRID_STEP * 1.5)
    ? `<br/>內插示性波高 Hs ≈ ${best.v} m`
    : '<br/>此處不在浮標有效內插範圍（最近浮標逾 120km）';
  L.popup().setLatLng(e.latlng).setContent(html).openOn(map);
});

let chart;
function showChart(s) {
  document.getElementById('chartTitle').textContent =
    `${s.meta.StationNameLocal} — Wave Height & Period (last 2 days)`;
  const labels = s.hs_series.map(p => p.t.slice(5, 16).replace('T', ' '));
  const hs = s.hs_series.map(p => p.v);
  const perMap = {}; s.period_series.forEach(p => perMap[p.t] = p.v);
  const per = s.hs_series.map(p => perMap[p.t] ?? null);
  if (chart) chart.destroy();
  chart = new Chart(document.getElementById('chart'), {
    type: 'line',
    data: { labels, datasets: [
      { label: 'Significant Wave Height (m)', data: hs, borderColor: '#4fc3f7',
        backgroundColor: 'rgba(79,195,247,.15)', fill: true, tension: .3, yAxisID: 'y',
        pointRadius: 3.5, pointHoverRadius: 6, pointBackgroundColor: '#4fc3f7', borderWidth: 2 },
      { label: 'Wave Period (s)', data: per, borderColor: '#ffb74d', tension: .3, yAxisID: 'y1',
        spanGaps: true, pointRadius: 3, pointHoverRadius: 6, pointBackgroundColor: '#ffb74d', borderWidth: 2 }
    ]},
    options: { responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#cdd9e5' } } },
      scales: {
        x: { ticks: { color: '#8aa0b8', maxTicksLimit: 8 }, grid: { color: '#1c2c46' } },
        y: { position: 'left', title: { display: true, text: 'Hs (m)', color: '#4fc3f7' },
             ticks: { color: '#8aa0b8' }, grid: { color: '#1c2c46' } },
        y1: { position: 'right', title: { display: true, text: 'Period (s)', color: '#ffb74d' },
              ticks: { color: '#8aa0b8' }, grid: { display: false } }
      } }
  });
}
showChart(DATA[0]);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
