"""高解析(小區域)漁場棲地預測：用 NODASS 開放衛星影像(免 token)合成小區
高解析 SST 與葉綠素網格，計算海溫鋒面，並輸出各魚種高解析棲地適合度。

目標：把預測尺度從「浮標間 50–120km 內插」縮小到「衛星 ~1km、小漁場尺度」。
流程：
  1. 取目標小區內、指定日期窗的多個衛星場景(SST=SLNT_S3_SST, CHL=GOCI_CHL)。
  2. 各場景以圖例色帶數位化成數值，套陸地遮罩與合理值域，跨場景取平均(填補掃描帶/雲縫)。
  3. SST 鋒面 = 溫度梯度量值(鋒面常聚集餌料與魚群)。
  4. 棲地適合度 = 適溫隸屬(species_traits) × 餌料(葉綠素)因子，逐網格 0–100。
輸出：sdm/hires_grid.json、dashboard/hires.html。
資料來源：NODASS 開放衛星影像 API；魚種適溫見 species_traits.py。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

import fetch_satellite as FS
import sat_digitize as SD
from dashboard_common import SHARED_CSS, load_coast, nav_html, on_land
from species_traits import SPECIES

BASE = Path(__file__).resolve().parent
OUT_JSON = BASE / "sdm" / "hires_grid.json"
OUT_HTML = BASE / "dashboard" / "hires.html"

# 目標小區(台灣東北部彭佳嶼－東海陸棚鋒面帶，高生產力漁場)與解析度
TARGET = (121.6, 123.4, 24.4, 26.2)     # (west, east, south, north)
STEP = 0.02                              # ~2km 高解析
DATE1, DATE2 = "2021-03-01", "2021-03-16"
MAX_SCENES = 40

VAR = {"sst": ("SLNT_S3_SST", (8.0, 33.0)),    # (ClassCode, 合理值域)
       "chl": ("GOCI_CHL", (0.02, 35.0))}
# 展示魚種(暖水表層 + 底棲)；皆用適溫窗，餌料因子用葉綠素
SHOW_SPECIES = ["白帶魚", "白腹鯖(花飛)", "鎖管(透抽)", "鬼頭刀"]


def composite(var: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    code, (vlo, vhi) = VAR[var]
    spec = SD.LEGEND_SPEC[code]
    lats = np.arange(TARGET[3], TARGET[2] - 1e-9, -STEP)
    lons = np.arange(TARGET[0], TARGET[1] + 1e-9, STEP)
    scenes = [r for r in FS.list_scenes(code, DATE1, DATE2) if FS.covers(r, TARGET)]
    print(f"{var}({code}): {len(scenes)} scenes cover target")
    stack = []
    lut = None
    for rec in scenes[:MAX_SCENES]:
        try:
            img = FS.download(rec["AccessImageURL"])
            if lut is None:
                leg = FS.download(rec["AccessLegendURL"])
                lut = SD.legend_lut(str(leg), spec["vmin"], spec["vmax"], spec["scale"])
            g = SD.sample_grid(str(img), FS.bbox_of(rec), lut[0], lut[1], lats, lons)
            g[(g < vlo) | (g > vhi)] = np.nan      # 去除背景/雲(色帶極值)
            stack.append(g)
        except Exception as e:  # noqa: BLE001
            print("  skip scene:", type(e).__name__)
    if not stack:
        return lats, lons, np.full((len(lats), len(lons)), np.nan, np.float32)
    arr = np.stack(stack)
    field = np.nanmean(arr, axis=0)
    return lats, lons, field


def mask_land(lats, lons, field):
    for iy, la in enumerate(lats):
        for ix, lo in enumerate(lons):
            if on_land(float(lo), float(la)):
                field[iy, ix] = np.nan
    return field


def sst_front(sst):
    """海溫鋒面強度：梯度量值(°C/格)，近似 °C/2km。"""
    gy, gx = np.gradient(np.nan_to_num(sst, nan=np.nanmean(sst)))
    f = np.hypot(gx, gy)
    f[np.isnan(sst)] = np.nan
    return f


def thermal(sst, sp):
    a, b, c, d = sp["sst_min"], sp["opt_lo"], sp["opt_hi"], sp["sst_max"]
    t = np.zeros_like(sst)
    t = np.where((sst >= b) & (sst <= c), 1.0, t)
    t = np.where((sst > a) & (sst < b), (sst - a) / (b - a), t)
    t = np.where((sst > c) & (sst < d), (d - sst) / (d - c), t)
    t = np.where((sst <= a) | (sst >= d), 0.0, t)
    return t


def main():
    month = int(DATE1[5:7])
    la_s, lo_s, sst = composite("sst")
    _, _, chl = composite("chl")
    sst = mask_land(la_s, lo_s, sst)
    chl = mask_land(la_s, lo_s, chl)
    front = sst_front(sst)

    # 葉綠素餌料因子：log 正規化 0.05→2 mg/m3 對應 0→1
    chl_norm = np.clip((np.log10(chl) - np.log10(0.05)) /
                       (np.log10(2.0) - np.log10(0.05)), 0, 1)

    by_name = {sp["name"]: sp for sp in SPECIES}
    suit = {}
    for nm in SHOW_SPECIES:
        sp = by_name.get(nm)
        if not sp:
            continue
        season = 1.0 if month in sp["season"] else 0.55
        th = thermal(sst, sp) * season
        s = 100.0 * th * (0.6 + 0.4 * chl_norm)        # 適溫 × 餌料因子
        suit[nm] = s

    cells = []
    for iy in range(len(la_s)):
        for ix in range(len(lo_s)):
            v = sst[iy, ix]
            if np.isnan(v):
                continue
            cell = {"lat": round(float(la_s[iy]), 3), "lon": round(float(lo_s[ix]), 3),
                    "sst": round(float(v), 2),
                    "chl": None if np.isnan(chl[iy, ix]) else round(float(chl[iy, ix]), 3),
                    "front": None if np.isnan(front[iy, ix]) else round(float(front[iy, ix]), 3),
                    "s": {nm: (None if np.isnan(suit[nm][iy, ix])
                               else round(float(suit[nm][iy, ix]), 1)) for nm in suit}}
            cells.append(cell)

    meta = {"bbox": TARGET, "step": STEP, "window": [DATE1, DATE2],
            "species": list(suit), "n_sst_valid": int(np.isfinite(sst).sum()),
            "source": "NODASS 開放衛星影像 (Sentinel-3 SST, GOCI 葉綠素)"}
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps({"meta": meta, "cells": cells},
                                   ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    print(f"cells={len(cells)}  sst valid={meta['n_sst_valid']}  "
          f"sst range={np.nanmin(sst):.1f}-{np.nanmax(sst):.1f}  -> {OUT_JSON.name}")
    write_html(meta, cells)


def write_html(meta, cells):
    html = (HTML.replace("__CSS__", SHARED_CSS)
                .replace("__NAV__", nav_html("hires"))
                .replace("__COAST__", load_coast())
                .replace("__DATA__", json.dumps({"meta": meta, "cells": cells},
                                                ensure_ascii=False, separators=(",", ":")))
                .replace("__TS__", datetime.now().strftime("%Y-%m-%d %H:%M")))
    OUT_HTML.parent.mkdir(exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUT_HTML.name}")


HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NODASS 高解析小區漁場棲地</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>__CSS__</style></head><body>
<header><h1>NODASS 高解析小區漁場棲地預測(衛星 ~2km)</h1>
<div class="sub">資料來源：NODASS 開放衛星影像 API(Sentinel-3 海溫、GOCI 葉綠素)｜小區高解析合成｜產生 __TS__</div></header>
__NAV__
<div class="ctrl">
  <label for="layer">圖層：</label>
  <select id="layer"></select>
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
  <b>方法</b>：以圖例色帶將開放衛星影像數位化為數值，套陸地遮罩與合理值域，跨多場景平均以填補掃描帶/雲縫。
  <b>海溫鋒面</b>=溫度梯度量值(鋒面聚集餌料與魚群)。<b>棲地適合度</b>=魚種適溫隸屬 × 葉綠素餌料因子。<br/>
  <b>意義</b>：解析度 ~2km，遠細於浮標 50–120km 內插，可呈現小漁場尺度的鋒面與棲地熱區。
  漁獲量/CPUE 標籤尚在尋找，取得後可校正為真正的魚群量預測。對齊 SDG 14。
</div></div></div>
<script>
const DATA=__DATA__, COAST=__COAST__;
const cells=DATA.cells, meta=DATA.meta;
const map=L.map('map').setView([(meta.bbox[2]+meta.bbox[3])/2,(meta.bbox[0]+meta.bbox[1])/2],9);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:18}).addTo(map);
map.createPane('land'); map.getPane('land').style.zIndex='450';
L.geoJSON(COAST,{pane:'land',interactive:false,style:{fillColor:'#26344d',fillOpacity:1,color:'#6f8db3',weight:1}}).addTo(map);
const STEP=meta.step, gl=L.layerGroup().addTo(map);

function jet(t){t=Math.max(0,Math.min(1,t));const r=Math.max(0,Math.min(1,1.5-Math.abs(4*t-3))),
  g=Math.max(0,Math.min(1,1.5-Math.abs(4*t-2))),b=Math.max(0,Math.min(1,1.5-Math.abs(4*t-1)));
  return `rgb(${(r*255)|0},${(g*255)|0},${(b*255)|0})`;}
function val(c,layer){if(layer==='sst')return c.sst;if(layer==='chl')return c.chl;if(layer==='front')return c.front;return c.s[layer];}

const layers=[['sst','海溫 SST (°C)',[18,28]],['chl','葉綠素 (mg/m³,log)',[-1.3,0.5]],['front','海溫鋒面強度',[0,1.2]]];
meta.species.forEach(sp=>layers.push([sp,'棲地適合度：'+sp,[0,100]]));
const sel=document.getElementById('layer');
layers.forEach(([k,t])=>{const o=document.createElement('option');o.value=k;o.textContent=t;sel.appendChild(o);});
sel.onchange=()=>draw(sel.value);

function draw(layer){gl.clearLayers();
  const meta3=layers.find(l=>l[0]===layer); let[lo,hi]=meta3[2];
  let n=0,sum=0,mx=-1e9;
  cells.forEach(c=>{let v=val(c,layer); if(v==null)return;
    let t; if(layer==='chl'){t=(Math.log10(Math.max(0.01,v))-lo)/(hi-lo);}else{t=(v-lo)/(hi-lo);}
    L.rectangle([[c.lat-STEP/2,c.lon-STEP/2],[c.lat+STEP/2,c.lon+STEP/2]],
      {stroke:false,fillColor:jet(t),fillOpacity:0.72}).addTo(gl);
    n++;sum+=v;mx=Math.max(mx,v);});
  document.getElementById('kpi').innerHTML=
    `<div>網格數<b>${n}</b></div><div>解析度<b>~2km</b></div>`+
    `<div>平均<b>${(sum/n).toFixed(2)}</b></div><div>最高<b>${mx.toFixed(2)}</b></div>`;
  const grad='linear-gradient(90deg,rgb(0,0,255),rgb(0,255,255),rgb(0,255,0),rgb(255,255,0),rgb(255,0,0))';
  document.getElementById('legend').innerHTML=meta3[1]+
    `<div style="margin-top:4px;width:160px;height:12px;border-radius:3px;background:${grad}"></div>低 → 高`;
  document.getElementById('hint').textContent=
    layer.length>3&&!['sst','chl'].includes(layer)?'金黃/紅為棲地適合度高之小區熱區':'';
}
map.on('click',e=>{const la=e.latlng.lat,lo=e.latlng.lng;let best=null,bd=1e9;
  cells.forEach(c=>{const d=Math.abs(c.lat-la)+Math.abs(c.lon-lo);if(d<bd){bd=d;best=c;}});
  let h=`座標 ${la.toFixed(3)}, ${lo.toFixed(3)}`;
  if(best&&bd<=STEP*2){h+=`<br/>SST ${best.sst}°C`+(best.chl!=null?`　葉綠素 ${best.chl} mg/m³`:'')+
    (best.front!=null?`<br/>鋒面強度 ${best.front}`:'');
    Object.entries(best.s).forEach(([k,v])=>{if(v!=null)h+=`<br/>${k} 適合度 ${v}`;});}
  else h+='<br/>此處無有效衛星數值(雲/掃描帶外)';
  L.popup().setLatLng(e.latlng).setContent(h).openOn(map);});
document.getElementById('note').innerHTML=
  `合成日期窗：${meta.window[0]} ~ ${meta.window[1]}<br/>有效 SST 網格：${meta.n_sst_valid}<br/>來源：${meta.source}`;
draw('sst');
</script></body></html>
"""

if __name__ == "__main__":
    main()
