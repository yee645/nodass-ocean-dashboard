"""未來 5 天高解析漁場棲地預報：用氣象署 OCM 海流模式(公開、免授權)的
數值預報場(SST、海流)，套魚種適溫模型，輸出今日與未來數日的高解析棲地適合度。

資料來源：中央氣象署 OCM 海流模式 OPeNDAP(oceanapi.cwa.gov.tw)。0.025° 數值場、120 小時逐時預報。
本頁取小區、選定預報時段(今日/+1/+2/+3 天)，與機制式適溫×季節結合，輸出棲地與海流漂移。
輸出：sdm/forecast_grid.json、dashboard/forecast.html。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

import fetch_ocm_forecast as OCM
from dashboard_common import SHARED_CSS, load_coast, nav_html
from species_traits import SPECIES

BASE = Path(__file__).resolve().parent
OUT_JSON = BASE / "sdm" / "forecast_grid.json"
OUT_HTML = BASE / "dashboard" / "forecast.html"

TARGET = (119.8, 123.4, 23.3, 26.4)      # 小區(北部+東北+東部陸棚)
STRIDE = 2                                # OCM 0.025° × 2 = 0.05°(~5km)
LEAD_DAYS = [0, 1, 2, 3]                  # 今日、+1、+2、+3 天(受預報長度與起報日限制)
SHOW_SPECIES = ["鬼頭刀", "鎖管(透抽)", "白帶魚", "白腹鯖(花飛)"]


def thermal_suit(sst, sp, month):
    a, b, c, d = sp["sst_min"], sp["opt_lo"], sp["opt_hi"], sp["sst_max"]
    t = np.zeros_like(sst)
    t = np.where((sst >= b) & (sst <= c), 1.0, t)
    t = np.where((sst > a) & (sst < b), (sst - a) / (b - a), t)
    t = np.where((sst > c) & (sst < d), (d - sst) / (d - c), t)
    t = np.where((sst <= a) | (sst >= d), 0.0, t)
    season = 1.0 if month in sp["season"] else 0.55
    return 100.0 * t * season


def pick_leads(valids):
    """依目標天數選最接近的預報時間索引(今日 00:00 起算)。"""
    base = dt.datetime.combine(dt.date.today(), dt.time(0))
    chosen = []
    for dday in LEAD_DAYS:
        target = base + dt.timedelta(days=dday)
        i = int(np.argmin([abs((v - target).total_seconds()) for v in valids]))
        if i not in [c[0] for c in chosen]:
            chosen.append((i, dday, valids[i]))
    return chosen


def main():
    init = OCM.find_latest_init()
    if not init:
        print("找不到可用 OCM 預報")
        return
    th = OCM.time_hours(init)
    valids = [OCM.hours_to_dt(int(h)) for h in th]
    leads = pick_leads(valids)
    month = dt.date.today().month
    print(f"init={init}  forecast {valids[0]:%m-%d %H:%M}~{valids[-1]:%m-%d %H:%M}  "
          f"leads={[(d, v.strftime('%m-%d')) for _, d, v in leads]}")

    by_name = {sp["name"]: sp for sp in SPECIES}
    grids = {}
    lat_ref = lon_ref = mask = None
    for ti, dday, v in leads:
        lats, lons, sst = OCM.subset(init, "SST", ti, TARGET, STRIDE)
        _, _, u = OCM.subset(init, "UCURR", ti, TARGET, STRIDE)
        _, _, w = OCM.subset(init, "VCURR", ti, TARGET, STRIDE)
        if lat_ref is None:
            lat_ref, lon_ref = lats, lons
            mask = np.isfinite(sst)
        cspd = np.hypot(u, w)
        layer = {"sst": sst, "u": u, "w": w, "cspd": cspd}
        for nm in SHOW_SPECIES:
            sp = by_name.get(nm)
            if sp:
                layer["S:" + nm] = thermal_suit(sst, sp, month)
        grids[dday] = layer
        print(f"  +{dday}d {v:%m-%d %H:%M}: SST {np.nanmin(sst):.1f}-{np.nanmax(sst):.1f}  "
              f"流速max {np.nanmax(cspd):.2f} m/s")

    # 以第一個預報的有效(海域)格為固定網格
    ys, xs = np.where(mask)
    cells = [{"lat": round(float(lat_ref[y]), 3), "lon": round(float(lon_ref[x]), 3)}
             for y, x in zip(ys, xs)]

    def arr(field, dday):
        a = grids[dday][field][ys, xs]
        return [None if not np.isfinite(v) else round(float(v), 3) for v in a]

    data = {}
    for dday in [d for _, d, _ in leads]:
        data[str(dday)] = {
            "sst": arr("sst", dday), "u": arr("u", dday), "w": arr("w", dday),
            "cspd": arr("cspd", dday),
            "s": {nm: arr("S:" + nm, dday) for nm in SHOW_SPECIES if "S:" + nm in grids[dday]},
        }

    meta = {"init": init, "bbox": TARGET, "step": RES_DEG(),
            "month": month, "species": SHOW_SPECIES,
            "leads": [{"d": d, "valid": v.strftime("%Y-%m-%d %H:%M")} for _, d, v in leads],
            "source": "中央氣象署 OCM 海流模式 (oceanapi.cwa.gov.tw, OPeNDAP)"}
    OUT_JSON.parent.mkdir(exist_ok=True)
    payload = {"meta": meta, "cells": cells, "data": data}
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    print(f"cells={len(cells)} leads={len(data)} -> {OUT_JSON.name}")
    write_html(payload)


def RES_DEG():
    return round(OCM.RES * STRIDE, 4)


def write_html(payload):
    html = (HTML.replace("__CSS__", SHARED_CSS)
                .replace("__NAV__", nav_html("fc"))
                .replace("__COAST__", load_coast())
                .replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                .replace("__TS__", dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
    OUT_HTML.parent.mkdir(exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUT_HTML.name}")


HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NODASS 未來高解析漁場棲地預報</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>__CSS__
  .cur{width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;
    border-bottom:10px solid #cfe8ff;filter:drop-shadow(0 0 1px #000);}
</style></head><body>
<header><h1>NODASS 未來高解析漁場棲地預報（今日 + 未來數日）</h1>
<div class="sub">資料來源：中央氣象署 OCM 海流模式（OPeNDAP 數值預報，0.05° 取樣）｜套魚種適溫模型｜產生 __TS__</div></header>
__NAV__
<div class="ctrl">
  <label for="lead">預報時段：</label><select id="lead"></select>
  <label for="layer">圖層：</label><select id="layer"></select>
  <label><input type="checkbox" id="curToggle" checked />顯示海流向量</label>
  <span class="note" id="hint"></span>
</div>
<div class="wrap">
  <div id="map"></div>
  <div class="side">
    <div class="panel"><div class="kpi" id="kpi"></div>
      <div class="legend" id="legend" style="margin-top:8px;"></div></div>
    <div class="panel"><div class="note" id="note"></div></div>
  </div>
</div>
<div class="wrap"><div class="panel" style="flex:1;"><div class="note">
  <b>方法</b>：氣象署 OCM 海流模式提供未來 5 天、0.025° 的數值 SST 與海流場(本頁取小區、0.05° 取樣)。
  棲地適合度=魚種適溫隸屬×季節因子(套用預報 SST)；海流向量取自預報 UCURR/VCURR，示意魚群可能漂移方向。<br/>
  <b>意義</b>：把高解析棲地推進到「今日與未來數日」，且為政府公開數值預報、免授權。<br/>
  <b>限制</b>：預報長度與起報日決定可及天數；為棲地(環境)預報，非漁獲量；葉綠素未納入(OCM 無)。資料來源須註明中央氣象署。對齊 SDG 14。
</div></div></div>
<script>
const P=__DATA__, COAST=__COAST__, cells=P.cells, meta=P.meta, DATA=P.data;
const STEP=meta.step;
const map=L.map('map').setView([(meta.bbox[2]+meta.bbox[3])/2,(meta.bbox[0]+meta.bbox[1])/2],9);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:18}).addTo(map);
map.createPane('land'); map.getPane('land').style.zIndex='450';
L.geoJSON(COAST,{pane:'land',interactive:false,style:{fillColor:'#26344d',fillOpacity:1,color:'#6f8db3',weight:1}}).addTo(map);
map.createPane('top'); map.getPane('top').style.zIndex='460';
const gridRenderer=L.canvas({padding:0.5}), gl=L.layerGroup().addTo(map), cl=L.layerGroup().addTo(map);

function jet(t){t=Math.max(0,Math.min(1,t));const r=Math.max(0,Math.min(1,1.5-Math.abs(4*t-3))),
  g=Math.max(0,Math.min(1,1.5-Math.abs(4*t-2))),b=Math.max(0,Math.min(1,1.5-Math.abs(4*t-1)));
  return `rgb(${(r*255)|0},${(g*255)|0},${(b*255)|0})`;}

const leadSel=document.getElementById('lead'), laySel=document.getElementById('layer');
meta.leads.forEach(L0=>{const o=document.createElement('option');o.value=L0.d;
  o.textContent=(L0.d===0?'今日':'+'+L0.d+'天')+'（'+L0.valid.slice(5,16)+'）';leadSel.appendChild(o);});
const layers=[['sst','海溫 SST (°C)',[18,30]],['cspd','海流速 (m/s)',[0,1.5]]];
meta.species.forEach(sp=>layers.push(['S:'+sp,'棲地適合度：'+sp,[0,100]]));
layers.forEach(([k,t])=>{const o=document.createElement('option');o.value=k;o.textContent=t;laySel.appendChild(o);});

function curArrows(d){cl.clearLayers(); if(!document.getElementById('curToggle').checked)return;
  const D=DATA[d]; for(let i=0;i<cells.length;i+=7){const u=D.u[i],w=D.w[i]; if(u==null||w==null)continue;
    const sp=Math.hypot(u,w); if(sp<0.05)continue;
    const deg=(Math.atan2(u,w)*180/Math.PI+360)%360;
    L.marker([cells[i].lat,cells[i].lon],{pane:'top',icon:L.divIcon({className:'',
      html:`<div class="cur" style="transform:rotate(${deg}deg)"></div>`,iconSize:[8,10],iconAnchor:[4,5]})}).addTo(cl);}}

function draw(){const d=leadSel.value, layer=laySel.value, D=DATA[d], vals=layer.startsWith('S:')?D.s[layer.slice(2)]:D[layer];
  const meta3=layers.find(l=>l[0]===layer); const[lo,hi]=meta3[2];
  gl.clearLayers(); let n=0,sum=0,mx=-1e9;
  cells.forEach((c,i)=>{const v=vals[i]; if(v==null)return;
    const t=(v-lo)/(hi-lo);
    L.rectangle([[c.lat-STEP/2,c.lon-STEP/2],[c.lat+STEP/2,c.lon+STEP/2]],
      {stroke:false,fillColor:jet(t),fillOpacity:0.72,renderer:gridRenderer}).addTo(gl);
    n++;sum+=v;mx=Math.max(mx,v);});
  curArrows(d);
  const lead=meta.leads.find(L0=>String(L0.d)===String(d));
  document.getElementById('kpi').innerHTML=
    `<div>預報時刻<b>${lead.valid.slice(5,16)}</b></div><div>解析度<b>~5km</b></div>`+
    `<div>平均<b>${(sum/n).toFixed(2)}</b></div><div>最高<b>${mx.toFixed(2)}</b></div>`;
  const grad='linear-gradient(90deg,rgb(0,0,255),rgb(0,255,255),rgb(0,255,0),rgb(255,255,0),rgb(255,0,0))';
  document.getElementById('legend').innerHTML=meta3[1]+
    `<div style="margin-top:4px;width:160px;height:12px;border-radius:3px;background:${grad}"></div>低 → 高　▲海流向量`;
  document.getElementById('hint').textContent=layer.startsWith('S:')?'金黃/紅為棲地適合度高之未來熱區':'';
}
leadSel.onchange=draw; laySel.onchange=draw; document.getElementById('curToggle').onchange=draw;
map.on('click',e=>{const la=e.latlng.lat,lo=e.latlng.lng;let bi=-1,bd=1e9;
  cells.forEach((c,i)=>{const dd=Math.abs(c.lat-la)+Math.abs(c.lon-lo);if(dd<bd){bd=dd;bi=i;}});
  const d=leadSel.value,D=DATA[d];let h=`座標 ${la.toFixed(3)}, ${lo.toFixed(3)}`;
  if(bi>=0&&bd<=STEP*2&&D.sst[bi]!=null){h+=`<br/>SST ${D.sst[bi]}°C　海流 ${D.cspd[bi]} m/s`;
    Object.entries(D.s).forEach(([k,a])=>{if(a[bi]!=null)h+=`<br/>${k} 適合度 ${a[bi]}`;});}
  else h+='<br/>此處無預報值(陸地/範圍外)';
  L.popup().setLatLng(e.latlng).setContent(h).openOn(map);});
document.getElementById('note').innerHTML=
  `起報：${meta.init.slice(0,4)}-${meta.init.slice(4,6)}-${meta.init.slice(6,8)} 00Z<br/>`+
  `可及預報：${meta.leads.map(L0=>(L0.d===0?'今日':'+'+L0.d+'d')).join('、')}<br/>來源：${meta.source}`;
draw();
</script></body></html>
"""

if __name__ == "__main__":
    main()
