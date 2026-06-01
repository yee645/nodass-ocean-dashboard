"""未來數日高解析漁場棲地預報。

環境來源：
  - 中央氣象署 OCM 海流模式 OPeNDAP(公開)：未來 SST、海流(UCURR/VCURR)，0.025° 數值預報。
  - NODASS 開放 GOCI 葉綠素：取當月多年氣候平均，作為餌料(生產力)因子。
棲地適合度 = 魚種適溫隸屬 × 季節因子 × 葉綠素餌料因子(0–100)。
輸出今日/+1/+2/+3 天高解析棲地 + 海流向量。介面：分段按鈕 + 魚種勾選晶片(複選顯示最適魚種)。
輸出：sdm/forecast_grid.json、dashboard/forecast.html。
資料來源須註明：中央氣象署 OCM 海流模式、NODASS/GOCI 葉綠素。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

import fetch_ocm_forecast as OCM
import fetch_satellite as FS
import sat_digitize as SD
from dashboard_common import SHARED_CSS, load_coast, nav_html
from species_traits import SPECIES

BASE = Path(__file__).resolve().parent
OUT_JSON = BASE / "sdm" / "forecast_grid.json"
OUT_HTML = BASE / "dashboard" / "forecast.html"

TARGET = (119.0, 123.2, 21.7, 26.2)      # 環島(含西部/西南/南部沿海)
STRIDE = 2                                # OCM 0.025° × 2 = 0.05°(~5km)
LEAD_DAYS = [0, 1, 2, 3]
SHOW_SPECIES = ["鬼頭刀", "鎖管(透抽)", "白帶魚", "白腹鯖(花飛)", "正鰹", "飛魚"]
CHL_YEARS = [2020, 2019]                  # GOCI 葉綠素氣候平均取用年份(archive 約止於 2020)
MAX_CHL_SCENES = 24


def thermal(sst, sp):
    a, b, c, d = sp["sst_min"], sp["opt_lo"], sp["opt_hi"], sp["sst_max"]
    t = np.zeros_like(sst)
    t = np.where((sst >= b) & (sst <= c), 1.0, t)
    t = np.where((sst > a) & (sst < b), (sst - a) / (b - a), t)
    t = np.where((sst > c) & (sst < d), (d - sst) / (d - c), t)
    t = np.where((sst <= a) | (sst >= d), 0.0, t)
    return t


def pick_leads(valids):
    base = dt.datetime.combine(dt.date.today(), dt.time(0))
    chosen = []
    for dday in LEAD_DAYS:
        target = base + dt.timedelta(days=dday)
        i = int(np.argmin([abs((v - target).total_seconds()) for v in valids]))
        if i not in [c[0] for c in chosen]:
            chosen.append((i, dday, valids[i]))
    return chosen


def chl_climatology(lat_ref, lon_ref, month):
    """當月 GOCI 葉綠素多年氣候平均(內插到 OCM 網格)。回傳 2D 與 log 正規化餌料因子。"""
    spec = SD.LEGEND_SPEC["GOCI_CHL"]
    lut, stack = None, []
    for yr in CHL_YEARS:
        d1 = f"{yr}-{month:02d}-01"
        d2 = f"{yr}-{month:02d}-28"
        try:
            scenes = [r for r in FS.list_scenes("GOCI_CHL", d1, d2) if FS.covers(r, TARGET)]
        except Exception:
            scenes = []
        for rec in scenes[:MAX_CHL_SCENES // len(CHL_YEARS)]:
            try:
                img = FS.download(rec["AccessImageURL"])
                if lut is None:
                    leg = FS.download(rec["AccessLegendURL"])
                    lut = SD.legend_lut(str(leg), spec["vmin"], spec["vmax"], spec["scale"])
                g = SD.sample_grid(str(img), FS.bbox_of(rec), lut[0], lut[1], lat_ref, lon_ref)
                g[(g < 0.02) | (g > 35)] = np.nan
                stack.append(g)
            except Exception:
                pass
    if not stack:
        chl = np.full((len(lat_ref), len(lon_ref)), np.nan, dtype=np.float32)
    else:
        chl = np.nanmean(np.stack(stack), axis=0)

    # 餌料因子用「補洞 + 平滑」後的連續葉綠素場，避免覆蓋邊界造成棲地圖硬跳變(斷層)
    from scipy import ndimage
    norm = np.clip((np.log10(np.where(chl > 0, chl, np.nan)) - np.log10(0.05)) /
                   (np.log10(2.0) - np.log10(0.05)), 0, 1)
    m = np.isfinite(norm)
    if m.sum() > 0:
        idx = ndimage.distance_transform_edt(~m, return_distances=False, return_indices=True)
        filled = norm[tuple(idx)]                      # 以最近有效值補洞
        chl_norm = ndimage.gaussian_filter(filled, sigma=2.0)   # 高斯平滑成連續場
    else:
        chl_norm = np.zeros_like(chl)
    print(f"  GOCI 葉綠素氣候平均：場景 {len(stack)}  有效格 {int(m.sum())}（餌料因子已補洞+平滑為連續場）")
    return chl, chl_norm                               # chl=原始(供顯示)，chl_norm=連續(供因子)


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
    show = [nm for nm in SHOW_SPECIES if nm in by_name]
    lead_env = {}
    lat_ref = lon_ref = mask = None
    for ti, dday, v in leads:
        lats, lons, sst = OCM.subset(init, "SST", ti, TARGET, STRIDE)
        _, _, u = OCM.subset(init, "UCURR", ti, TARGET, STRIDE)
        _, _, w = OCM.subset(init, "VCURR", ti, TARGET, STRIDE)
        if lat_ref is None:
            lat_ref, lon_ref, mask = lats, lons, np.isfinite(sst)
        lead_env[dday] = {"sst": sst, "u": u, "w": w, "cspd": np.hypot(u, w)}
        print(f"  +{dday}d {v:%m-%d %H:%M}: SST {np.nanmin(sst):.1f}-{np.nanmax(sst):.1f}")

    chl, chl_norm = chl_climatology(lat_ref, lon_ref, month)
    prod = 0.6 + 0.4 * np.nan_to_num(chl_norm, nan=0.0)     # 餌料因子(無葉綠素時保守 0.6)

    ys, xs = np.where(mask)
    cells = [{"lat": round(float(lat_ref[y]), 3), "lon": round(float(lon_ref[x]), 3)}
             for y, x in zip(ys, xs)]

    def col(arr2d, nd, integer=False):
        out = []
        for y, x in zip(ys, xs):
            val = arr2d[y, x]
            out.append(None if not np.isfinite(val) else (int(round(val)) if integer else round(float(val), nd)))
        return out

    data = {}
    for dday in [d for _, d, _ in leads]:
        e = lead_env[dday]
        sst = e["sst"]
        season = {nm: (1.0 if month in by_name[nm]["season"] else 0.55) for nm in show}
        suit = {nm: 100.0 * thermal(sst, by_name[nm]) * season[nm] * prod for nm in show}
        data[str(dday)] = {
            "sst": col(sst, 2), "u": col(e["u"], 3), "w": col(e["w"], 3),
            "cspd": col(e["cspd"], 3),
            "s": {nm: col(suit[nm], 0, integer=True) for nm in show},
        }

    meta = {"init": init, "bbox": TARGET, "step": round(OCM.RES * STRIDE, 4),
            "month": month, "species": show,
            "leads": [{"d": d, "valid": v.strftime("%Y-%m-%d %H:%M")} for _, d, v in leads],
            "source": "中央氣象署 OCM 海流模式 + NODASS/GOCI 葉綠素氣候平均"}
    payload = {"meta": meta, "cells": cells, "chl": col(chl, 3), "data": data}
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    print(f"cells={len(cells)} leads={len(data)} species={len(show)} -> {OUT_JSON.name}")
    write_html(payload)


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
<div class="sub">資料來源：中央氣象署 OCM 海流模式 + NODASS/GOCI 葉綠素氣候平均｜0.05° 取樣｜產生 __TS__</div></header>
__NAV__
<div class="ctrl">
  <strong style="color:#cdd9e5;font-size:0.85rem;">預報時段</strong><span class="seg" id="leadSeg"></span>
</div>
<div class="ctrl">
  <strong style="color:#cdd9e5;font-size:0.85rem;">圖層</strong><span class="seg" id="baseSeg"></span>
  <label><input type="checkbox" id="curToggle" checked />海流向量</label>
</div>
<div class="ctrl" id="spRow" style="display:none;align-items:flex-start;">
  <strong style="color:#cdd9e5;font-size:0.85rem;padding-top:6px;">魚種<br/><span class="note">可複選</span></strong>
  <span class="chips" id="spChips"></span>
  <span style="display:flex;flex-direction:column;gap:4px;">
    <button class="toolbtn" id="spAll">全選</button><button class="toolbtn" id="spNone">清除</button></span>
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
  <b>方法</b>：氣象署 OCM 提供未來數日 0.025° 數值 SST 與海流(本頁 0.05° 取樣)；
  葉綠素取 GOCI 當月多年氣候平均作餌料因子。<b>棲地適合度=適溫隸屬 × 季節 × 餌料因子</b>。
  海流向量取自預報 UCURR/VCURR，示意魚群可能漂移方向。<br/>
  <b>意義</b>：把高解析棲地推進到今日與未來數日，政府公開數值預報、免授權。<br/>
  <b>限制</b>：可及天數受預報長度限制；葉綠素為氣候平均(非當日)；為棲地(環境)預報非漁獲量。
  資料來源須註明中央氣象署 OCM 與 GOCI。對齊 SDG 14。
</div></div></div>
<script>
const P=__DATA__, COAST=__COAST__, cells=P.cells, meta=P.meta, DATA=P.data, CHL=P.chl;
const STEP=meta.step, N=cells.length;
const map=L.map('map').setView([(meta.bbox[2]+meta.bbox[3])/2,(meta.bbox[0]+meta.bbox[1])/2],8);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:18}).addTo(map);
map.createPane('land'); map.getPane('land').style.zIndex='450';
L.geoJSON(COAST,{pane:'land',interactive:false,style:{fillColor:'#26344d',fillOpacity:1,color:'#6f8db3',weight:1}}).addTo(map);
map.createPane('top'); map.getPane('top').style.zIndex='460';
const gridRenderer=L.canvas({padding:0.5}), gl=L.layerGroup().addTo(map), cl=L.layerGroup().addTo(map);

function jet(t){t=Math.max(0,Math.min(1,t));const r=Math.max(0,Math.min(1,1.5-Math.abs(4*t-3))),
  g=Math.max(0,Math.min(1,1.5-Math.abs(4*t-2))),b=Math.max(0,Math.min(1,1.5-Math.abs(4*t-1)));
  return `rgb(${(r*255)|0},${(g*255)|0},${(b*255)|0})`;}
function rect(i,color){L.rectangle([[cells[i].lat-STEP/2,cells[i].lon-STEP/2],[cells[i].lat+STEP/2,cells[i].lon+STEP/2]],
  {stroke:false,fillColor:color,fillOpacity:0.72,renderer:gridRenderer}).addTo(gl);}
const GRAD='linear-gradient(90deg,rgb(0,0,255),rgb(0,255,255),rgb(0,255,0),rgb(255,255,0),rgb(255,0,0))';
function setLegend(t){document.getElementById('legend').innerHTML=t+
  `<div style="margin-top:4px;width:160px;height:12px;border-radius:3px;background:${GRAD}"></div>低 → 高　▲海流向量`;}
function setKpi(a){document.getElementById('kpi').innerHTML=a.map(([k,v])=>`<div>${k}<b>${v}</b></div>`).join('');}

const BASE=[['sst','海溫 SST (°C)',18,30,'lin'],['cspd','海流速 (m/s)',0,1.5,'lin'],
  ['chl','葉綠素氣候平均 (mg/m³)',-1.3,0.5,'log'],['habitat','棲地適合度(選魚種)',0,100,'lin']];
let baseKey='sst', leadKey=String(meta.leads[0].d);
const checked=new Set(meta.species.slice(0,2).map(nm=>nm));

const leadSeg=document.getElementById('leadSeg');
meta.leads.forEach(L0=>{const b=document.createElement('button');b.dataset.k=String(L0.d);
  b.textContent=(L0.d===0?'今日':'+'+L0.d+'天')+'('+L0.valid.slice(5,10)+')';
  b.onclick=()=>{leadKey=String(L0.d);[...leadSeg.children].forEach(c=>c.classList.toggle('on',c.dataset.k===leadKey));draw();};
  leadSeg.appendChild(b);}); leadSeg.firstChild.classList.add('on');

const baseSeg=document.getElementById('baseSeg');
BASE.forEach(([k,label])=>{const b=document.createElement('button');b.textContent=label;b.dataset.k=k;
  b.onclick=()=>{baseKey=k;[...baseSeg.children].forEach(c=>c.classList.toggle('on',c.dataset.k===k));
    document.getElementById('spRow').style.display=(k==='habitat')?'flex':'none';draw();};
  baseSeg.appendChild(b);}); baseSeg.firstChild.classList.add('on');

const chips=document.getElementById('spChips');
meta.species.forEach(nm=>{const lab=document.createElement('label');lab.dataset.k=nm;
  lab.innerHTML=`<input type="checkbox" ${checked.has(nm)?'checked':''}/> ${nm}`;lab.classList.toggle('on',checked.has(nm));
  lab.querySelector('input').onchange=e=>{e.target.checked?checked.add(nm):checked.delete(nm);lab.classList.toggle('on',e.target.checked);draw();};
  chips.appendChild(lab);});
document.getElementById('spAll').onclick=()=>{checked.clear();meta.species.forEach(nm=>checked.add(nm));sync();draw();};
document.getElementById('spNone').onclick=()=>{checked.clear();sync();draw();};
function sync(){[...chips.children].forEach(l=>{const on=checked.has(l.dataset.k);l.classList.toggle('on',on);l.querySelector('input').checked=on;});}

function curArrows(){cl.clearLayers(); if(!document.getElementById('curToggle').checked)return;
  const D=DATA[leadKey]; for(let i=0;i<N;i+=7){const u=D.u[i],w=D.w[i]; if(u==null||w==null)continue;
    if(Math.hypot(u,w)<0.05)continue; const deg=(Math.atan2(u,w)*180/Math.PI+360)%360;
    L.marker([cells[i].lat,cells[i].lon],{pane:'top',icon:L.divIcon({className:'',
      html:`<div class="cur" style="transform:rotate(${deg}deg)"></div>`,iconSize:[8,10],iconAnchor:[4,5]})}).addTo(cl);}}

function draw(){gl.clearLayers();
  const D=DATA[leadKey];
  if(baseKey==='habitat'){drawHabitat(D);curArrows();return;}
  const m=BASE.find(b=>b[0]===baseKey),lo=m[2],hi=m[3],log=m[4]==='log';
  const arr=baseKey==='chl'?CHL:D[baseKey];
  let n=0,sum=0,mx=-1e9;
  for(let i=0;i<N;i++){let v=arr[i]; if(v==null)continue;
    let t=log?(Math.log10(Math.max(0.01,v))-lo)/(hi-lo):(v-lo)/(hi-lo);
    rect(i,jet(t)); n++;sum+=v;mx=Math.max(mx,v);}
  curArrows();
  const lead=meta.leads.find(L0=>String(L0.d)===leadKey);
  setKpi([['預報時刻',lead.valid.slice(5,16)],['解析度','~5km'],['平均',(sum/n).toFixed(2)],['最高',mx.toFixed(2)]]);
  setLegend(m[1]+(baseKey==='chl'?'(靜態)':'')); document.getElementById('hint').textContent='';
}
function drawHabitat(D){const keys=[...checked];
  if(!keys.length){setKpi([['提示','請勾選魚種']]);setLegend('棲地適合度');return;}
  let n=0,sum=0,mx=0;
  for(let i=0;i<N;i++){let best=null;
    for(const nm of keys){const v=D.s[nm]?D.s[nm][i]:null; if(v!=null&&(best==null||v>best))best=v;}
    if(best==null)continue; rect(i,jet(best/100)); n++;sum+=best;mx=Math.max(mx,best);}
  const lead=meta.leads.find(L0=>String(L0.d)===leadKey);
  setKpi([['預報時刻',lead.valid.slice(5,16)],['選取魚種',keys.length],['平均',(sum/n).toFixed(0)],['最高',mx]]);
  setLegend(keys.length>1?'最適魚種棲地(複選取最大值)':'棲地適合度');
  document.getElementById('hint').textContent=keys.length>1?'每格顯示所選魚種中最高的適合度':'';
}
document.getElementById('curToggle').onchange=draw;
map.on('click',e=>{const la=e.latlng.lat,lo=e.latlng.lng;let bi=-1,bd=1e9;
  for(let i=0;i<N;i++){const d=Math.abs(cells[i].lat-la)+Math.abs(cells[i].lon-lo);if(d<bd){bd=d;bi=i;}}
  const D=DATA[leadKey];let h=`座標 ${la.toFixed(3)}, ${lo.toFixed(3)}`;
  if(bi>=0&&bd<=STEP*2&&D.sst[bi]!=null){h+=`<br/>SST ${D.sst[bi]}°C　海流 ${D.cspd[bi]} m/s`+
    (CHL[bi]!=null?`　葉綠素 ${CHL[bi]}`:'');
    const ks=baseKey==='habitat'&&checked.size?[...checked]:meta.species;
    const lines=ks.map(nm=>{const v=D.s[nm]?D.s[nm][bi]:null;return v==null?null:`${nm} ${v}`;}).filter(Boolean);
    if(lines.length)h+='<br/>適合度：'+lines.join('、');}
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
