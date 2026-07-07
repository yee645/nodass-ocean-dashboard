"""未來數日高解析漁場棲地預報。

環境來源：
  - 中央氣象署 OCM 海流模式 OPeNDAP(公開)：未來 SST、海流(UCURR/VCURR)、
    風速/風向(WS/WD)、潮位(WL)，0.025° 數值預報。
  - NODASS 開放 GOCI 葉綠素：取當月多年氣候平均，作為餌料(生產力)因子。
棲地適合度 = 魚種適溫隸屬 × 季節因子 × 葉綠素餌料因子(0–100)。
輸出今日/+1/+2/+3 天高解析棲地 + 海象安全層(風/流/潮)。
介面參考中央氣象署海象資訊平台(ocean.cwa.gov.tw)：基礎圖層切換 + 任一點預報 + 向量箭頭。
輸出：sdm/forecast_grid.json、dashboard/forecast.html。
資料來源須註明：中央氣象署 OCM 海流模式、NODASS/GOCI 葉綠素。
免責：海象僅供出航前參考，正式以中央氣象署官方海象/漁業氣象與海巡署警報為準。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

import fetch_ocm_forecast as OCM
import fetch_satellite as FS
import sat_digitize as SD
from dashboard_common import (INFO_MODAL_JS, SHARED_CSS, info_modal, load_coast,
                              nav_html)
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
        # P2 海象安全層：風速/風向/潮位(OCM 公開、免授權)
        _, _, ws = OCM.subset(init, "WS", ti, TARGET, STRIDE)
        _, _, wd = OCM.subset(init, "WD", ti, TARGET, STRIDE)
        _, _, wl = OCM.subset(init, "WL", ti, TARGET, STRIDE)
        if lat_ref is None:
            lat_ref, lon_ref, mask = lats, lons, np.isfinite(sst)
        lead_env[dday] = {"sst": sst, "u": u, "w": w, "cspd": np.hypot(u, w),
                          "ws": ws, "wd": wd, "wl": wl}
        print(f"  +{dday}d {v:%m-%d %H:%M}: SST {np.nanmin(sst):.1f}-{np.nanmax(sst):.1f}"
              f"  風 {np.nanmin(ws):.1f}-{np.nanmax(ws):.1f} m/s  潮位 {np.nanmin(wl):.2f}~{np.nanmax(wl):.2f} m")

    chl, chl_norm = chl_climatology(lat_ref, lon_ref, month)
    prod = 0.6 + 0.4 * np.nan_to_num(chl_norm, nan=0.0)     # 餌料因子(無葉綠素時保守 0.6)

    ys, xs = np.where(mask)
    cells = [{"lat": round(float(lat_ref[y]), 3), "lon": round(float(lon_ref[x]), 3)}
             for y, x in zip(ys, xs)]
    # P3 資料信心(出現點支持)：與 hires 同一函式，逐格依到最近出現點距離換算 0–1
    import build_hires as HR
    conf = HR.confidence_for_cells([c["lat"] for c in cells], [c["lon"] for c in cells])

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
            "ws": col(e["ws"], 2), "wd": col(e["wd"], 0, integer=True), "wl": col(e["wl"], 2),
            "s": {nm: col(suit[nm], 0, integer=True) for nm in show},
        }

    meta = {"init": init, "bbox": TARGET, "step": round(OCM.RES * STRIDE, 4),
            "month": month, "species": show,
            "leads": [{"d": d, "valid": v.strftime("%Y-%m-%d %H:%M")} for _, d, v in leads],
            "source": "中央氣象署 OCM 海流模式(SST/海流/風/潮位) + NODASS/GOCI 葉綠素氣候平均"}
    meta["has_conf"] = any(c is not None for c in conf)
    # P2 第二階段：CWA 波浪(示性波高 Hs)——有 .cwa_token 或快取才接入，否則優雅跳過(零回歸)
    meta["has_wave"] = False
    try:
        import fetch_cwa_wave as WAVE
        stations = WAVE.load_or_fetch()
        if stations:
            lead_valids = {d: v.strftime("%Y-%m-%d") for _, d, v in leads}
            hs_grid = WAVE.to_grid(stations, cells, lead_valids)
            if any(any(x is not None for x in c) for c in hs_grid.values()):
                for dday in [d for _, d, _ in leads]:
                    data[str(dday)]["hs"] = hs_grid.get(str(dday))
                meta["has_wave"] = True
                meta["source"] += " + 中央氣象署波浪預報(示性波高 Hs)"
                print(f"  波浪 Hs 已接入：{len(stations)} 站 IDW 上網格")
    except Exception as e:  # noqa: BLE001
        print("波浪接入略過：", type(e).__name__, str(e)[:80])
    payload = {"meta": meta, "cells": cells, "chl": col(chl, 3), "conf": conf, "data": data}
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    print(f"cells={len(cells)} leads={len(data)} species={len(show)} -> {OUT_JSON.name}")
    write_html(payload)


MODAL_BODY = """
  <div class="note">
  <b>海象安全層(P2)</b>：中央氣象署 OCM 提供未來數日 0.025° 數值場(本頁 0.05° 取樣)——
  海溫、海流(UCURR/VCURR)、<b>風速/風向(WS/WD)</b>、<b>潮位(WL)</b>，皆公開免授權。
  潮位以發散色階呈現高低潮；風向採中央氣象署慣例(風的來向)，箭頭轉為示意吹向。
  <b>註</b>：OCM 為海流模式，其地面風場(WS)量值偏弱，本頁風速僅以相對色階呈現空間分布，
  絕對風力請以中央氣象署陸上/海上強風特報為準。<br/><br/>
  <b>棲地</b>：適合度=適溫隸屬 × 季節 × 餌料因子(GOCI 當月氣候平均葉綠素)；海流向量示意魚群可能漂移。
  <b>資料信心</b>：每格依到最近物種出現點距離換算 0–1(遠離資料處模型外推、信心低)，可單看信心層或勾「低信心淡化」。<br/><br/>
  <b>波浪</b>：示性波高(Hs)不在 OCM，改接中央氣象署波浪/沿海預報開放資料，以 IDW 內插為
  <b>Hs (m)</b> 圖層(設定免費金鑰 .cwa_token 後於重建時自動啟用；未設定則本頁不顯示波浪層，
  即時波浪仍可見「極端浪況預警」浮標頁)。<br/><br/>
  <b>限制</b>：可及天數受預報長度限制；葉綠素為氣候平均(非當日)；波浪為沿海海區預報之空間內插；
  本層為環境/棲地預報非漁獲量。<b>出海安全正式以中央氣象署官方海象/漁業氣象與海巡署警報為準</b>。
  資料來源須註明中央氣象署 OCM 與 GOCI。對齊 SDG 14。
  </div>
  <div class="note" id="note" style="margin-top:10px;border-top:1px solid #24344f;padding-top:10px;"></div>
"""


def write_html(payload):
    html = (HTML.replace("__CSS__", SHARED_CSS)
                .replace("__NAV__", nav_html("fc"))
                .replace("__COAST__", load_coast())
                .replace("__MODAL__", info_modal("關於本頁與資料說明", MODAL_BODY))
                .replace("__MODALJS__", INFO_MODAL_JS)
                .replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                .replace("__TS__", dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
    OUT_HTML.parent.mkdir(exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUT_HTML.name}")


HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant" class="cwa"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NODASS 未來海象與漁場棲地預報</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>__CSS__
  .cur{width:0;height:0;border-left:2.5px solid transparent;border-right:2.5px solid transparent;
    border-bottom:9px solid #cfe8ff;filter:drop-shadow(0 0 1px #000);}
  .wnd{width:0;height:0;border-left:2.5px solid transparent;border-right:2.5px solid transparent;
    border-bottom:10px solid #ffd27f;filter:drop-shadow(0 0 1px #000);}
</style>
<script>if(window.top!==window.self)document.documentElement.classList.add('embedded');</script>
</head><body>
<button class="panel-reopen" id="leftReopen" title="開啟資訊" aria-label="開啟資訊">&#9776;</button>
<div class="leftpanel" id="leftPanel">
  <div class="lpane-head">
    <div class="lpane-title">NODASS 未來海象與漁場棲地預報</div>
    <button class="lpane-x" id="leftCollapse" title="收合" aria-label="收合">&times;</button>
  </div>
  <div class="lpane-sub">海象安全層(風/流/潮) + 多魚種棲地｜中央氣象署 OCM + NODASS/GOCI｜介面參考 ocean.cwa.gov.tw｜產生 __TS__</div>
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
      <div><div class="lp-label">基礎圖層</div><span class="seg" id="baseSeg"></span></div>
      <div class="lp-toggles">
        <label><input type="checkbox" id="curToggle" checked />海流向量</label>
        <label><input type="checkbox" id="windToggle" />風向量</label>
        <label title="信心 < 0.3 的格子(遠離出現點、模型外推)降透明度標示"><input type="checkbox" id="lowconf" />低信心淡化</label>
      </div>
      <div id="spRow" style="display:none;">
        <div class="lp-label">魚種（可複選）</div>
        <span class="chips" id="spChips"></span>
        <div style="display:flex;gap:6px;margin-top:6px;">
          <button class="toolbtn" id="spAll">全選</button><button class="toolbtn" id="spNone">清除</button></div>
        <span class="note" id="hint"></span>
      </div>
      <div class="kpi" id="kpi"></div>
      <div class="legend" id="legend"></div>
    </div>
  </div>
  <div class="timebar">
    <button class="tbtn" id="playBtn" title="自動播放" aria-label="自動播放">&#9654;</button>
    <div class="tslider">
      <div class="tlabel" id="tlabel">預報時段</div>
      <input type="range" id="leadRange" min="0" max="3" step="1" value="0" />
      <div class="tticks" id="tticks"></div>
    </div>
  </div>
  <div class="floathint">出航前參考：風(向)、海流、潮位。正式以
    <b style="color:#ffd27f;">中央氣象署官方海象/漁業氣象與海巡署警報</b>為準（點右上 <b>i</b> 看完整說明）。</div>
</div>
__MODAL__
<script>
const P=__DATA__, COAST=__COAST__, cells=P.cells, meta=P.meta, DATA=P.data, CHL=P.chl, CONF=P.conf||null;
const STEP=meta.step, N=cells.length;
const map=L.map('map').setView([(meta.bbox[2]+meta.bbox[3])/2,(meta.bbox[0]+meta.bbox[1])/2],8);
map.zoomControl.setPosition('bottomright');   // 移開左上，避免被左側標題面板遮住
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:18}).addTo(map);
map.createPane('land'); map.getPane('land').style.zIndex='450';
L.geoJSON(COAST,{pane:'land',interactive:false,style:{fillColor:'#26344d',fillOpacity:1,color:'#6f8db3',weight:1}}).addTo(map);
map.createPane('top'); map.getPane('top').style.zIndex='460';
const gridRenderer=L.canvas({padding:0.5}), gl=L.layerGroup().addTo(map), cl=L.layerGroup().addTo(map),
  wlg=L.layerGroup().addTo(map);

function jet(t){t=Math.max(0,Math.min(1,t));const r=Math.max(0,Math.min(1,1.5-Math.abs(4*t-3))),
  g=Math.max(0,Math.min(1,1.5-Math.abs(4*t-2))),b=Math.max(0,Math.min(1,1.5-Math.abs(4*t-1)));
  return `rgb(${(r*255)|0},${(g*255)|0},${(b*255)|0})`;}
function hx(h){return [parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)];}
function stops(arr,t){t=Math.max(0,Math.min(1,t));for(let i=1;i<arr.length;i++){if(t<=arr[i][0]){
  const a=arr[i-1],b=arr[i],f=(t-a[0])/((b[0]-a[0])||1),c1=hx(a[1]),c2=hx(b[1]);
  return `rgb(${(c1[0]+(c2[0]-c1[0])*f)|0},${(c1[1]+(c2[1]-c1[1])*f)|0},${(c1[2]+(c2[2]-c1[2])*f)|0})`;}}
  return arr[arr.length-1][1];}
// 風速採近中央氣象署蒲福風級配色；潮位採發散色階(低潮藍-高潮紅)
const WINDPAL=[[0,'#2c7fb8'],[0.18,'#41b6c4'],[0.36,'#a1dab4'],[0.5,'#ffffb2'],[0.66,'#fecc5c'],[0.82,'#f03b20'],[1,'#7a0177']];
const TIDEPAL=[[0,'#2166ac'],[0.5,'#f2f4f7'],[1,'#b2182b']];
const CONFPAL=[[0,'#d73027'],[0.25,'#fc8d59'],[0.5,'#fee08b'],[0.75,'#d9ef8b'],[1,'#1a9850']];
const PAL={jet:jet,wind:t=>stops(WINDPAL,t),tide:t=>stops(TIDEPAL,t),conf:t=>stops(CONFPAL,t)};
const LOWCONF=0.3;
function cellOpacity(i){if(!CONF||!document.getElementById('lowconf').checked)return 0.72;
  return (CONF[i]==null||CONF[i]<LOWCONF)?0.16:0.72;}
function gradCss(name){const f=PAL[name];let s=[];for(let i=0;i<=10;i++)s.push(f(i/10)+' '+(i*10)+'%');
  return 'linear-gradient(90deg,'+s.join(',')+')';}
function beaufort(ms){const b=[0.3,1.6,3.4,5.5,8,10.8,13.9,17.2,20.8,24.5,28.5,32.7];let f=0;
  for(let i=0;i<b.length;i++){if(ms>=b[i])f=i+1;}return f;}
function rect(i,color){L.rectangle([[cells[i].lat-STEP/2,cells[i].lon-STEP/2],[cells[i].lat+STEP/2,cells[i].lon+STEP/2]],
  {stroke:false,fillColor:color,fillOpacity:0.72,renderer:gridRenderer}).addTo(gl);}
function setLegend(t,name,lohi){const pal=name||'jet';const extra=lohi?` <span class="note">${lohi}</span>`:'';
  document.getElementById('legend').innerHTML=t+
  `<div style="margin-top:4px;width:170px;height:12px;border-radius:3px;background:${gradCss(pal)}"></div>低 → 高`+extra;}
function setKpi(a){document.getElementById('kpi').innerHTML=a.map(([k,v])=>`<div>${k}<b>${v}</b></div>`).join('');}

// 第3,4欄為色階上下界；null 表示依當前資料動態縮放(OCM 海流模式地面風場量值偏弱，採相對色階)
const BASE=[['sst','海溫 SST (°C)',18,30,'lin','jet'],
  ['cspd','海流速 (m/s)',0,1.5,'lin','jet'],
  ['ws','風速 (m/s，模式場)',null,null,'lin','wind'],
  ['wl','潮位 (m)',-1.2,1.2,'lin','tide'],
  ['hs','示性波高 Hs (m)',0,4,'lin','jet'],
  ['conf','資料信心(出現點支持)',0,1,'lin','conf'],
  ['chl','葉綠素氣候平均 (mg/m³)',-1.3,0.5,'log','jet'],
  ['habitat','棲地適合度(選魚種)',0,100,'lin','jet']];
if(!meta.has_conf){const ci=BASE.findIndex(b=>b[0]==='conf');if(ci>=0)BASE.splice(ci,1);}
if(!meta.has_wave){const wi=BASE.findIndex(b=>b[0]==='hs');if(wi>=0)BASE.splice(wi,1);}
let baseKey='sst', leadKey=String(meta.leads[0].d);
const checked=new Set(meta.species.slice(0,2).map(nm=>nm));

// 時間軸滑桿(可拖曳切換預報時段) + 播放鈕 + 日期刻度
const LEADS=meta.leads, leadRange=document.getElementById('leadRange'), tlabel=document.getElementById('tlabel'),
  tticks=document.getElementById('tticks');
leadRange.max=LEADS.length-1;
function leadText(i){const L0=LEADS[i];return (L0.d===0?'今日':'+'+L0.d+'天')+' ('+L0.valid.slice(5,16)+')';}
LEADS.forEach(L0=>{const s=document.createElement('span');s.textContent=(L0.d===0?'今日':'+'+L0.d+'天');tticks.appendChild(s);});
function setLead(i){i=Math.max(0,Math.min(LEADS.length-1,i));leadRange.value=i;leadKey=String(LEADS[i].d);
  tlabel.textContent=leadText(i);draw();}
leadRange.oninput=()=>setLead(+leadRange.value);
let playTimer=null;const playBtn=document.getElementById('playBtn');
playBtn.onclick=function(){if(playTimer){clearInterval(playTimer);playTimer=null;playBtn.innerHTML='&#9654;';return;}
  playBtn.innerHTML='&#10074;&#10074;';playTimer=setInterval(()=>setLead((+leadRange.value+1)%LEADS.length),1100);};

const baseSeg=document.getElementById('baseSeg');
BASE.forEach(([k,label])=>{const b=document.createElement('button');b.textContent=label;b.dataset.k=k;
  b.onclick=()=>{baseKey=k;[...baseSeg.children].forEach(c=>c.classList.toggle('on',c.dataset.k===k));
    document.getElementById('spRow').style.display=(k==='habitat')?'flex':'none';draw();};
  baseSeg.appendChild(b);}); baseSeg.firstChild.classList.add('on');

const chips=document.getElementById('spChips');
meta.species.forEach(nm=>{const lab=document.createElement('label');lab.dataset.k=nm;
  lab.innerHTML=`<input type="checkbox" ${checked.has(nm)?'checked':''}/> ${nm}`;lab.classList.toggle('on',checked.has(nm));
  lab.querySelector('input').onchange=e=>{e.target.checked?checked.add(nm):checked.delete(nm);lab.classList.toggle('on',e.target.checked);draw();__emitSp();};
  chips.appendChild(lab);});
document.getElementById('spAll').onclick=()=>{checked.clear();meta.species.forEach(nm=>checked.add(nm));sync();draw();__emitSp();};
document.getElementById('spNone').onclick=()=>{checked.clear();sync();draw();__emitSp();};
function sync(){[...chips.children].forEach(l=>{const on=checked.has(l.dataset.k);l.classList.toggle('on',on);l.querySelector('input').checked=on;});}

function curArrows(){cl.clearLayers(); if(!document.getElementById('curToggle').checked)return;
  const D=DATA[leadKey]; for(let i=0;i<N;i+=7){const u=D.u[i],w=D.w[i]; if(u==null||w==null)continue;
    if(Math.hypot(u,w)<0.05)continue; const deg=(Math.atan2(u,w)*180/Math.PI+360)%360;
    L.marker([cells[i].lat,cells[i].lon],{pane:'top',icon:L.divIcon({className:'',
      html:`<div class="cur" style="transform:rotate(${deg}deg)"></div>`,iconSize:[5,9],iconAnchor:[2.5,4.5]})}).addTo(cl);}}

// 風向量：WD 為氣象風向(來向)，箭頭轉為「吹向」(WD+180)以利視覺；箭長隨風速
function windArrows(){wlg.clearLayers(); if(!document.getElementById('windToggle').checked)return;
  const D=DATA[leadKey]; if(!D.ws)return;
  for(let i=0;i<N;i+=7){const s=D.ws[i],d=D.wd[i]; if(s==null||d==null||s<0.5)continue;
    const blowTo=(d+180)%360, len=Math.min(12,Math.round(7+s));
    L.marker([cells[i].lat,cells[i].lon],{pane:'top',icon:L.divIcon({className:'',
      html:`<div class="wnd" style="transform:rotate(${blowTo}deg);border-bottom-width:${len}px"></div>`,
      iconSize:[6,len],iconAnchor:[3,len/2]})}).addTo(wlg);}}

function draw(){gl.clearLayers();
  const D=DATA[leadKey];
  if(baseKey==='habitat'){drawHabitat(D);curArrows();windArrows();return;}
  const m=BASE.find(b=>b[0]===baseKey),log=m[4]==='log',pal=PAL[m[5]];
  const isConf=baseKey==='conf';
  const arr=baseKey==='chl'?CHL:isConf?CONF:D[baseKey];
  let lo=m[2],hi=m[3];
  if(lo==null||hi==null){let a=1e9,b=-1e9;for(let i=0;i<N;i++){const v=arr[i];if(v==null)continue;a=Math.min(a,v);b=Math.max(b,v);}
    lo=a; hi=(b>a)?b:a+1;}                       // 動態相對色階
  let n=0,sum=0,mn=1e9,mx=-1e9;
  for(let i=0;i<N;i++){let v=arr[i]; if(v==null)continue;
    let t=log?(Math.log10(Math.max(0.01,v))-lo)/(hi-lo):(v-lo)/(hi-lo);
    rect(i,pal(t),isConf?0.72:cellOpacity(i)); n++;sum+=v;mn=Math.min(mn,v);mx=Math.max(mx,v);}
  curArrows();windArrows();
  const lead=meta.leads.find(L0=>String(L0.d)===leadKey);
  let kpi=[['預報時刻',lead.valid.slice(5,16)],['解析度','~5km'],['平均',(sum/n).toFixed(2)],['最高',mx.toFixed(2)]];
  if(baseKey==='ws')kpi=[['預報時刻',lead.valid.slice(5,16)],['風速範圍',mn.toFixed(2)+'~'+mx.toFixed(2)+' m/s'],
    ['平均',(sum/n).toFixed(2)+' m/s'],['模式','OCM 地面風']];
  if(baseKey==='wl')kpi=[['預報時刻',lead.valid.slice(5,16)],['潮位範圍',mn.toFixed(2)+'~'+mx.toFixed(2)+' m'],
    ['平均',(sum/n).toFixed(2)+' m']];
  if(isConf){const low=arr.filter(v=>v!=null&&v<LOWCONF).length;
    kpi=[['網格數',n],['平均信心',(sum/n).toFixed(2)],['低信心格',low],['門檻','<'+LOWCONF]];}
  setKpi(kpi);
  const lohi=baseKey==='ws'?`相對色階 ${lo.toFixed(2)}–${hi.toFixed(2)} m/s（絕對風力以氣象署強風特報為準）`
    :baseKey==='wl'?'低潮 ← 0 → 高潮':isConf?'資料信心 0低 → 1高':'';
  setLegend(m[1]+(baseKey==='chl'?'(靜態)':''),m[5],lohi);
  document.getElementById('hint').textContent=
    (!isConf&&CONF&&document.getElementById('lowconf').checked)?'淡色格為低信心(遠離出現點/模型外推)':'';
}
function drawHabitat(D){const keys=[...checked];
  if(!keys.length){setKpi([['提示','請勾選魚種']]);setLegend('棲地適合度');return;}
  let n=0,sum=0,mx=0;
  for(let i=0;i<N;i++){let best=null;
    for(const nm of keys){const v=D.s[nm]?D.s[nm][i]:null; if(v!=null&&(best==null||v>best))best=v;}
    if(best==null)continue; rect(i,jet(best/100),cellOpacity(i)); n++;sum+=best;mx=Math.max(mx,best);}
  const lead=meta.leads.find(L0=>String(L0.d)===leadKey);
  setKpi([['預報時刻',lead.valid.slice(5,16)],['選取魚種',keys.length],['平均',(sum/n).toFixed(0)],['最高',mx]]);
  setLegend(keys.length>1?'最適魚種棲地(複選取最大值)':'棲地適合度','jet');
  const fade=CONF&&document.getElementById('lowconf').checked;
  document.getElementById('hint').textContent=
    fade?'淡色格為低信心(遠離出現點)':(keys.length>1?'每格顯示所選魚種中最高的適合度':'');
}
document.getElementById('curToggle').onchange=draw;
document.getElementById('windToggle').onchange=draw;
document.getElementById('lowconf').onchange=draw;

// P1.5 跨時段魚種同步適配器(平台 iframe 用；單獨開頁時 parent===window 不影響)
window.__getSpecies=()=>[...checked];
window.__setSpecies=names=>{checked.clear();meta.species.forEach(nm=>{if(names.indexOf(nm)>=0)checked.add(nm);});sync();draw();};
window.addEventListener('message',e=>{const d=e.data||{};if(d.nsp==='fishsync'&&d.type==='apply'&&window.__setSpecies)window.__setSpecies(d.names||[]);});
function __emitSp(){try{if(window.parent!==window)parent.postMessage({nsp:'fishsync',type:'changed',names:window.__getSpecies()},'*');}catch(e){}}
try{if(window.parent!==window)parent.postMessage({nsp:'fishsync',type:'ready'},'*');}catch(e){}
map.on('click',e=>{const la=e.latlng.lat,lo=e.latlng.lng;let bi=-1,bd=1e9;
  for(let i=0;i<N;i++){const d=Math.abs(cells[i].lat-la)+Math.abs(cells[i].lon-lo);if(d<bd){bd=d;bi=i;}}
  const D=DATA[leadKey];let h=`座標 ${la.toFixed(3)}, ${lo.toFixed(3)}`;
  if(bi>=0&&bd<=STEP*2&&D.sst[bi]!=null){h+=`<br/>SST ${D.sst[bi]}°C　海流 ${D.cspd[bi]} m/s`+
    (CHL[bi]!=null?`　葉綠素 ${CHL[bi]}`:'');
    const ws=D.ws?D.ws[bi]:null,wd=D.wd?D.wd[bi]:null,wlv=D.wl?D.wl[bi]:null;
    if(ws!=null)h+=`<br/>風速 ${ws} m/s（${beaufort(ws)} 級`+(wd!=null?`，向 ${wd}°`:'')+'）'+
      (wlv!=null?`　潮位 ${wlv} m`:'');
    if(CONF&&CONF[bi]!=null)h+=`<br/>資料信心 ${CONF[bi]}（${CONF[bi]<LOWCONF?'低，模型外推':CONF[bi]<0.6?'中':'高'}）`;
    const ks=baseKey==='habitat'&&checked.size?[...checked]:meta.species;
    const lines=ks.map(nm=>{const v=D.s[nm]?D.s[nm][bi]:null;return v==null?null:`${nm} ${v}`;}).filter(Boolean);
    if(lines.length)h+='<br/>適合度：'+lines.join('、');}
  else h+='<br/>此處無預報值(陸地/範圍外)';
  L.popup().setLatLng(e.latlng).setContent(h).openOn(map);});
document.getElementById('note').innerHTML=
  `起報：${meta.init.slice(0,4)}-${meta.init.slice(4,6)}-${meta.init.slice(6,8)} 00Z<br/>`+
  `可及預報：${meta.leads.map(L0=>(L0.d===0?'今日':'+'+L0.d+'d')).join('、')}<br/>來源：${meta.source}`;
setLead(0);   // 初始化時間軸滑桿與首張圖
// 右側圖層面板可收合(點標題列收合；點 i 不收合)
document.getElementById('lpHead').onclick=function(e){if(e.target.closest('#infoBtn'))return;
  document.getElementById('layerPanel').classList.toggle('collapsed');};
// 左側標題面板可收合/重開
var lP=document.getElementById('leftPanel'),lR=document.getElementById('leftReopen');
document.getElementById('leftCollapse').onclick=function(){lP.style.display='none';lR.style.display='flex';};
lR.onclick=function(){lP.style.display='';lR.style.display='none';};
// 全螢幕版型下確保地圖正確量測尺寸
setTimeout(function(){map.invalidateSize();},150);
window.addEventListener('resize',function(){map.invalidateSize();});
__MODALJS__
</script></body></html>
"""

if __name__ == "__main__":
    main()
