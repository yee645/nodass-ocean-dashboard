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

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

import fetch_satellite as FS
import sat_digitize as SD
from dashboard_common import (INFO_MODAL_JS, SHARED_CSS, info_modal, load_coast,
                              nav_html, on_land)
from species_traits import SPECIES

BASE = Path(__file__).resolve().parent
OUT_JSON = BASE / "sdm" / "hires_grid.json"
OUT_HTML = BASE / "dashboard" / "hires.html"
OCC_CSV = BASE / "sdm" / "occurrences.csv"
SDM_REPORT = BASE / "sdm" / "hires_sdm_report.csv"

# 目標區與解析度（可自由調整：擴大區域/改日期窗即可換不同漁場與季節）
TARGET = (119.8, 123.4, 22.0, 26.4)     # (west, east, south, north) 北+東+南；西界受 Sentinel-3 footprint 限制
STEP = 0.04                              # ~4km 高解析
DATE1, DATE2 = "2021-02-10", "2021-04-20"   # 早春窗（與春季出現點配對）
SEASON_MONTHS = {2, 3, 4}                # 與日期窗一致，用於篩選出現點季節
MAX_SCENES = 60
MIN_PRESENCE_SDM = 20                    # 高解析 SDM 驗證所需最少（區內）出現點(去重至網格)

VAR = {"sst": ("SLNT_S3_SST", (8.0, 33.0)),    # (ClassCode, 合理值域)
       "chl": ("GOCI_CHL", (0.02, 35.0))}
# 機制式(適溫×餌料)展示魚種
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


def confidence_for_cells(cell_lats, cell_lons, scale_deg: float = 0.3):
    """資料信心(P3)：每個輸出格點到最近物種出現點的距離 → exp(-(d/scale)^2)。
    出現點密集處(模型有實證支持)信心高；遠離資料、模型外推處信心低。
    單一來源函式：供 main() 與信心注入器共用。回傳與 cell 等長的 0–1 list(無資料為 None)。"""
    pts = []
    try:
        with open(OCC_CSV, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                pts.append((float(r["decimalLatitude"]), float(r["decimalLongitude"])))
    except FileNotFoundError:
        return [None] * len(cell_lats)
    if not pts:
        return [None] * len(cell_lats)
    from scipy.spatial import cKDTree
    tree = cKDTree(np.array(pts))
    d, _ = tree.query(np.column_stack([cell_lats, cell_lons]), k=1)
    conf = np.exp(-(d / scale_deg) ** 2)
    return [round(float(x), 3) for x in conf]


def thermal(sst, sp):
    a, b, c, d = sp["sst_min"], sp["opt_lo"], sp["opt_hi"], sp["sst_max"]
    t = np.zeros_like(sst)
    t = np.where((sst >= b) & (sst <= c), 1.0, t)
    t = np.where((sst > a) & (sst < b), (sst - a) / (b - a), t)
    t = np.where((sst > c) & (sst < d), (d - sst) / (d - c), t)
    t = np.where((sst <= a) | (sst >= d), 0.0, t)
    return t


def fit_hires_sdm(lats, lons, sst, chl, front):
    """把高解析環境(SST、log葉綠素、鋒面)與區內季節出現點配對，
    擬合 presence-only 高斯包絡 SDM，交叉驗證 AUC，回傳各魚種棲地適合度網格與報表。"""
    chl_log = np.log10(np.where(chl > 0, chl, np.nan))
    layers = [sst, chl_log, front]
    valid = np.isfinite(sst) & np.isfinite(chl_log) & np.isfinite(front)
    Z, stats = [], []
    for L in layers:
        m = float(np.nanmean(L[valid])); s = float(np.nanstd(L[valid])) or 1.0
        stats.append((m, s)); Z.append((L - m) / s)
    Zs = np.stack(Z, axis=2)                       # Ny×Nx×3
    Ny, Nx = sst.shape
    north, west = lats[0], lons[0]

    # 用區內所有出現點(去重至網格)；衛星合成場為代表性(早春)環境，
    # 季節一致性為已知限制(出現點橫跨年代/季節)，於報表與頁面說明。
    occ = defaultdict(set)
    with open(OCC_CSV, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            la, lo = float(r["decimalLatitude"]), float(r["decimalLongitude"])
            iy = int(round((north - la) / STEP)); ix = int(round((lo - west) / STEP))
            if 0 <= iy < Ny and 0 <= ix < Nx and valid[iy, ix]:
                occ[r["target_zh"]].add((iy, ix))

    bg_idx = np.argwhere(valid)
    rng = np.random.default_rng(42)
    bg = bg_idx[rng.choice(len(bg_idx), min(2000, len(bg_idx)), replace=False)]
    bgX = Zs[bg[:, 0], bg[:, 1]]

    def envelope(P):
        mu = P.mean(axis=0)
        cov = np.cov(P, rowvar=False) + np.eye(3) * 1e-3
        return mu, np.linalg.inv(cov)

    def score(X, mu, ci):
        d = X - mu
        return np.exp(-0.5 * np.einsum("ij,jk,ik->i", d, ci, d))

    def auc(pos, neg):
        allv = np.concatenate([pos, neg]); order = allv.argsort()
        ranks = np.empty(len(allv)); ranks[order] = np.arange(1, len(allv) + 1)
        u = ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2
        return round(float(u / (len(pos) * len(neg))), 3)

    results, report = {}, []
    for sp, cells in sorted(occ.items(), key=lambda kv: len(kv[1]), reverse=True):
        pc = np.array(sorted(cells))
        if len(pc) < MIN_PRESENCE_SDM:
            report.append((sp, len(pc), "skip-不足", ""))
            continue
        P = Zs[pc[:, 0], pc[:, 1]]
        # (1) 隨機 70/30 重複 5 次交叉驗證(偏樂觀，受空間自相關影響)
        aucs = []
        for k in range(5):
            idx = rng.permutation(len(P)); cut = int(len(P) * 0.7)
            tr, te = P[idx[:cut]], P[idx[cut:]]
            if len(te) < 5:
                continue
            mu, ci = envelope(tr)
            aucs.append(auc(score(te, mu, ci), score(bgX, mu, ci)))
        cv = round(float(np.mean(aucs)), 3) if aucs else float("nan")

        # (2) 空間分塊交叉驗證(leave-one-block-out, 0.6°方塊)：誠實值，降低空間自相關高估
        BS = 0.6
        blk = defaultdict(list)
        for r, (iy, ix) in enumerate(pc):
            blk[(int(lats[iy] // BS), int(lons[ix] // BS))].append(r)
        saucs = []
        if len(blk) >= 3:
            for hk, te_idx in blk.items():
                tr_idx = [r for r in range(len(pc)) if r not in set(te_idx)]
                if len(te_idx) < 3 or len(tr_idx) < 10:
                    continue
                mu, ci = envelope(P[tr_idx])
                saucs.append(auc(score(P[te_idx], mu, ci), score(bgX, mu, ci)))
        scv = round(float(np.mean(saucs)), 3) if saucs else float("nan")

        mu, ci = envelope(P)                       # 全資料擬合輸出網格
        s2d = np.full((Ny, Nx), np.nan, dtype=np.float32)
        vy, vx = np.where(valid)
        sc = score(Zs[vy, vx], mu, ci)
        sc = sc / sc.max() * 100.0
        s2d[vy, vx] = sc
        results[sp] = s2d
        report.append((sp, len(pc), cv, scv))
        print(f"  SDM species#{len(results)}: presence={len(pc)} randomCV={cv} spatialCV={scv}")

    with open(SDM_REPORT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["魚種", "區內出現點", "隨機CV-AUC", "空間分塊CV-AUC"])
        w.writerows(report)
    return results, [(sp, n, cv, scv) for sp, n, cv, scv in report
                     if not isinstance(cv, str)]


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

    # 資料驅動高解析 SDM（出現點 × 高解析環境，交叉驗證）
    sdm_grids, sdm_rep = fit_hires_sdm(la_s, lo_s, sst, chl, front)
    for nm, g in sdm_grids.items():
        suit["SDM:" + nm] = g

    # 欄位式(columnar)輸出：避免每格重複欄名，大幅縮小體積
    ys, xs = np.where(np.isfinite(sst))
    lat = [round(float(la_s[y]), 3) for y in ys]
    lon = [round(float(lo_s[x]), 3) for x in xs]

    def col(arr2d, nd):
        return [None if np.isnan(arr2d[y, x]) else round(float(arr2d[y, x]), nd)
                for y, x in zip(ys, xs)]

    def icol(arr2d):  # 適合度取整數,進一步縮小
        return [None if np.isnan(arr2d[y, x]) else int(round(arr2d[y, x]))
                for y, x in zip(ys, xs)]

    layers = {"sst": col(sst, 2), "chl": col(chl, 3), "front": col(front, 3)}
    layers["conf"] = confidence_for_cells(lat, lon)        # P3 資料信心(出現點支持)
    thermal_sp = [nm for nm in SHOW_SPECIES if nm in suit]
    sdm_sp = [sp for sp, n, cv, scv in sdm_rep]
    for nm in thermal_sp:
        layers["T:" + nm] = icol(suit[nm])
    for nm in sdm_sp:
        layers["S:" + nm] = icol(suit["SDM:" + nm])

    meta = {"bbox": TARGET, "step": STEP, "window": [DATE1, DATE2],
            "thermal": thermal_sp,
            "sdm": [{"name": sp, "n": n,
                     "auc": (None if scv != scv else scv),      # 空間CV(誠實值)
                     "rauc": (None if cv != cv else cv)}        # 隨機CV(參考)
                    for sp, n, cv, scv in sdm_rep],
            "n_sst_valid": int(len(lat)),
            "has_conf": any(c is not None for c in layers["conf"]),
            "source": "NODASS 開放衛星影像 (Sentinel-3 SST, GOCI 葉綠素)"}
    payload = {"meta": meta, "lat": lat, "lon": lon, "layers": layers}
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    print(f"cells={len(lat)}  sst range={np.nanmin(sst):.1f}-{np.nanmax(sst):.1f} "
          f"layers={len(layers)} -> {OUT_JSON.name}")
    write_html(payload)


MODAL_BODY = """
  <div class="note">
  <b>方法</b>：以圖例色帶將開放衛星影像數位化為數值，套陸地遮罩與合理值域，跨多場景平均以填補掃描帶/雲縫。
  <b>海溫鋒面</b>=溫度梯度量值(鋒面聚集餌料與魚群)。<b>適溫代理</b>=魚種適溫隸屬 × 葉綠素餌料因子。<br/><br/>
  <b>資料驅動 SDM</b>：把區內魚種出現點(TaiBIF/底拖/博物館/GBIF)與高解析環境(SST、log葉綠素、鋒面)配對，
  擬合 presence-only 高斯包絡模型。<b>準確度以空間分塊交叉驗證(leave-one-block-out, 0.6°)</b>呈現於魚種標籤，
  此值已抑制空間自相關高估，較隨機 70/30 CV 誠實(兩者皆記於 sdm/hires_sdm_report.csv)。<br/><br/>
  <b>資料信心(P3)</b>：每格依到最近物種出現點的距離換算 0–1 信心(出現點密集處信心高、遠離資料處模型外推信心低)；
  可單獨檢視「資料信心」圖層，或勾「低信心淡化」把信心 &lt;0.3 的格子淡化，提醒該處棲地預測證據較弱。<br/><br/>
  <b>意義</b>：解析度 ~4km，遠細於浮標 50–120km 內插，可呈現小漁場尺度的鋒面與棲地熱區。<br/>
  <b>限制</b>：衛星合成為早春代表場，出現點橫跨年代/季節(季節一致性為已知限制)；presence-only、無漁獲量。
  漁獲量/CPUE 標籤到位後可校正為真正的魚群量預測。對齊 SDG 14。
  </div>
  <div class="note" id="note" style="margin-top:10px;border-top:1px solid #24344f;padding-top:10px;"></div>
"""


def write_html(payload):
    html = (HTML.replace("__CSS__", SHARED_CSS)
                .replace("__NAV__", nav_html("hires"))
                .replace("__COAST__", load_coast())
                .replace("__MODAL__", info_modal("關於本頁與資料說明", MODAL_BODY))
                .replace("__MODALJS__", INFO_MODAL_JS)
                .replace("__DATA__", json.dumps(payload, ensure_ascii=False,
                                                separators=(",", ":")))
                .replace("__TS__", datetime.now().strftime("%Y-%m-%d %H:%M")))
    OUT_HTML.parent.mkdir(exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUT_HTML.name}")


HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant" class="cwa"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NODASS 高解析小區漁場棲地</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>__CSS__</style>
<script>if(window.top!==window.self)document.documentElement.classList.add('embedded');</script>
</head><body>
<button class="panel-reopen" id="leftReopen" title="開啟資訊" aria-label="開啟資訊">&#9776;</button>
<div class="leftpanel" id="leftPanel">
  <div class="lpane-head">
    <div class="lpane-title">NODASS 高解析小區漁場棲地預測（衛星 ~2km）</div>
    <button class="lpane-x" id="leftCollapse" title="收合" aria-label="收合">&times;</button>
  </div>
  <div class="lpane-sub">NODASS 開放衛星影像 API(Sentinel-3 海溫、GOCI 葉綠素)｜小區高解析合成｜產生 __TS__</div>
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
  <div class="floathint" id="dateHint">衛星合成日期窗（早春代表場）。詳細方法與限制請點右上 <b>i</b>。</div>
</div>
__MODAL__
<script>
const DATA=__DATA__, COAST=__COAST__;
const meta=DATA.meta, LAT=DATA.lat, LON=DATA.lon, L_=DATA.layers, STEP=meta.step, N=LAT.length;
const map=L.map('map').setView([(meta.bbox[2]+meta.bbox[3])/2,(meta.bbox[0]+meta.bbox[1])/2],9);
map.zoomControl.setPosition('bottomright');   // 移開左上，避免被左側標題面板遮住
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:18}).addTo(map);
map.createPane('land'); map.getPane('land').style.zIndex='450';
L.geoJSON(COAST,{pane:'land',interactive:false,style:{fillColor:'#26344d',fillOpacity:1,color:'#6f8db3',weight:1}}).addTo(map);
const gridRenderer=L.canvas({padding:0.5}), gl=L.layerGroup().addTo(map);

function jet(t){t=Math.max(0,Math.min(1,t));const r=Math.max(0,Math.min(1,1.5-Math.abs(4*t-3))),
  g=Math.max(0,Math.min(1,1.5-Math.abs(4*t-2))),b=Math.max(0,Math.min(1,1.5-Math.abs(4*t-1)));
  return `rgb(${(r*255)|0},${(g*255)|0},${(b*255)|0})`;}
function hx(h){return [parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)];}
function stops(arr,t){t=Math.max(0,Math.min(1,t));for(let i=1;i<arr.length;i++){if(t<=arr[i][0]){
  const a=arr[i-1],b=arr[i],f=(t-a[0])/((b[0]-a[0])||1),c1=hx(a[1]),c2=hx(b[1]);
  return `rgb(${(c1[0]+(c2[0]-c1[0])*f)|0},${(c1[1]+(c2[1]-c1[1])*f)|0},${(c1[2]+(c2[2]-c1[2])*f)|0})`;}}
  return arr[arr.length-1][1];}
// 信心色階(紅低-黃中-綠高，RdYlGn)
const CONFPAL=[[0,'#d73027'],[0.25,'#fc8d59'],[0.5,'#fee08b'],[0.75,'#d9ef8b'],[1,'#1a9850']];
function confcol(t){return stops(CONFPAL,t);}
const PAL={jet:jet,conf:confcol};
function gradCss(name){const f=PAL[name]||jet;let s=[];for(let i=0;i<=10;i++)s.push(f(i/10)+' '+(i*10)+'%');
  return 'linear-gradient(90deg,'+s.join(',')+')';}
function rect(i,color,op){L.rectangle([[LAT[i]-STEP/2,LON[i]-STEP/2],[LAT[i]+STEP/2,LON[i]+STEP/2]],
  {stroke:false,fillColor:color,fillOpacity:op==null?0.72:op,renderer:gridRenderer}).addTo(gl);}
function setLegend(t,name){document.getElementById('legend').innerHTML=t+
  `<div style="margin-top:4px;width:160px;height:12px;border-radius:3px;background:${gradCss(name||'jet')}"></div>低 → 高`;}
function setKpi(a){document.getElementById('kpi').innerHTML=a.map(([k,v])=>`<div>${k}<b>${v}</b></div>`).join('');}

// 低信心淡化：信心 < 此門檻的格子降透明度，視覺標示模型外推/低支持區
const CONF=L_.conf||null, LOWCONF=0.3;
function cellOpacity(i){if(!CONF||!document.getElementById('lowconf').checked)return 0.72;
  return (CONF[i]==null||CONF[i]<LOWCONF)?0.16:0.72;}

// 底圖圖層(單選)：環境 + 信心 + 棲地適合度
const BASE=[['sst','海溫 SST (°C)',18,28,'lin','jet'],['chl','葉綠素 (mg/m³)',-1.3,0.5,'log','jet'],
  ['front','海溫鋒面強度',0,1.2,'lin','jet'],['conf','資料信心(出現點支持)',0,1,'lin','conf'],
  ['habitat','棲地適合度(選魚種)',0,100,'lin','jet']];
// 魚種圖層鍵：適溫代理 T:、資料驅動 SDM S:
const SP=[];
meta.thermal.forEach(nm=>SP.push(['T:'+nm,nm+'(適溫)']));
(meta.sdm||[]).forEach(x=>SP.push(['S:'+x.name,`${x.name}(SDM 空間AUC ${x.auc==null?'—':x.auc})`]));

if(!meta.has_conf){const ci=BASE.findIndex(b=>b[0]==='conf');if(ci>=0)BASE.splice(ci,1);
  const lc=document.getElementById('lowconf');if(lc)lc.closest('label').style.display='none';}
let baseKey='sst'; const checked=new Set((meta.sdm||[]).slice(0,1).map(x=>'S:'+x.name));

// 建分段按鈕
const seg=document.getElementById('baseSeg');
BASE.forEach(([k,label])=>{const b=document.createElement('button');b.textContent=label;
  b.dataset.k=k; b.onclick=()=>{baseKey=k; [...seg.children].forEach(c=>c.classList.toggle('on',c.dataset.k===k));
    document.getElementById('spRow').style.display=(k==='habitat')?'flex':'none'; draw();};
  seg.appendChild(b);});
seg.firstChild.classList.add('on');
// 建魚種勾選晶片
const chips=document.getElementById('spChips');
SP.forEach(([k,label])=>{const lab=document.createElement('label');lab.dataset.k=k;
  lab.innerHTML=`<input type="checkbox" ${checked.has(k)?'checked':''}/> ${label}`;
  lab.classList.toggle('on',checked.has(k));
  lab.querySelector('input').onchange=e=>{e.target.checked?checked.add(k):checked.delete(k);
    lab.classList.toggle('on',e.target.checked); draw();__emitSp();};
  chips.appendChild(lab);});
document.getElementById('spAll').onclick=()=>{checked.clear();SP.forEach(([k])=>checked.add(k));syncChips();draw();__emitSp();};
document.getElementById('spNone').onclick=()=>{checked.clear();syncChips();draw();__emitSp();};
function syncChips(){[...chips.children].forEach(l=>{const on=checked.has(l.dataset.k);
  l.classList.toggle('on',on);l.querySelector('input').checked=on;});}

function draw(){gl.clearLayers();
  if(baseKey==='habitat'){drawHabitat();return;}
  const m=BASE.find(b=>b[0]===baseKey),lo=m[2],hi=m[3],log=m[4]==='log',pal=PAL[m[5]]||jet,arr=L_[baseKey];
  const isConf=baseKey==='conf';
  let n=0,sum=0,mx=-1e9;
  for(let i=0;i<N;i++){let v=arr[i]; if(v==null)continue;
    let t=log?(Math.log10(Math.max(0.01,v))-lo)/(hi-lo):(v-lo)/(hi-lo);
    rect(i,pal(t),isConf?0.72:cellOpacity(i)); n++;sum+=v;mx=Math.max(mx,v);}
  if(isConf){const lo3=arr.filter(v=>v!=null&&v<LOWCONF).length;
    setKpi([['網格數',n],['平均信心',(sum/n).toFixed(2)],['低信心格',lo3],['門檻','<'+LOWCONF]]);
    setLegend('資料信心(0低→1高)','conf');}
  else{setKpi([['網格數',n],['解析度','~4km'],['平均',(sum/n).toFixed(2)],['最高',mx.toFixed(2)]]);
    setLegend(m[1],'jet');}
  document.getElementById('hint').textContent=
    (!isConf&&CONF&&document.getElementById('lowconf').checked)?'淡色格為低信心(模型外推)':'';
}
function drawHabitat(){const keys=[...checked];
  if(!keys.length){setKpi([['提示','請勾選魚種']]);setLegend('棲地適合度');return;}
  let n=0,sum=0,mx=0;
  for(let i=0;i<N;i++){let best=null;
    for(const k of keys){const v=L_[k][i]; if(v!=null&&(best==null||v>best))best=v;}
    if(best==null)continue; rect(i,jet(best/100),cellOpacity(i)); n++;sum+=best;mx=Math.max(mx,best);}
  setKpi([['網格數',n],['選取魚種',keys.length],['平均',(sum/n).toFixed(0)],['最高',mx]]);
  setLegend(keys.length>1?'最適魚種棲地(複選取最大值)':'棲地適合度','jet');
  const fade=CONF&&document.getElementById('lowconf').checked;
  document.getElementById('hint').textContent=
    fade?'淡色格為低信心(遠離出現點)':(keys.length>1?'每格顯示所選魚種中最高的適合度':'');
}
document.getElementById('lowconf').onchange=draw;

// P1.5 跨時段魚種同步適配器：以魚種名(去 S:/T: 前綴)為共用鍵
window.__getSpecies=()=>[...new Set([...checked].map(k=>k.slice(2)))];
window.__setSpecies=names=>{checked.clear();const avail={};SP.forEach(([k])=>avail[k]=1);
  names.forEach(nm=>{if(avail['S:'+nm])checked.add('S:'+nm);else if(avail['T:'+nm])checked.add('T:'+nm);});
  syncChips();draw();};
window.addEventListener('message',e=>{const d=e.data||{};if(d.nsp==='fishsync'&&d.type==='apply'&&window.__setSpecies)window.__setSpecies(d.names||[]);});
function __emitSp(){try{if(window.parent!==window)parent.postMessage({nsp:'fishsync',type:'changed',names:window.__getSpecies()},'*');}catch(e){}}
try{if(window.parent!==window)parent.postMessage({nsp:'fishsync',type:'ready'},'*');}catch(e){}
map.on('click',e=>{const la=e.latlng.lat,lo=e.latlng.lng;let bi=-1,bd=1e9;
  for(let i=0;i<N;i++){const d=Math.abs(LAT[i]-la)+Math.abs(LON[i]-lo);if(d<bd){bd=d;bi=i;}}
  let h=`座標 ${la.toFixed(3)}, ${lo.toFixed(3)}`;
  if(bi>=0&&bd<=STEP*2&&L_.sst[bi]!=null){
    h+=`<br/>SST ${L_.sst[bi]}°C`+(L_.chl[bi]!=null?`　葉綠素 ${L_.chl[bi]} mg/m³`:'')+
       (L_.front[bi]!=null?`<br/>鋒面 ${L_.front[bi]}`:'')+
       (CONF&&CONF[bi]!=null?`<br/>資料信心 ${CONF[bi]}（${CONF[bi]<LOWCONF?'低，模型外推':CONF[bi]<0.6?'中':'高'}）`:'');
    const ks=baseKey==='habitat'&&checked.size?[...checked]:SP.map(s=>s[0]);
    const lines=ks.map(k=>{const v=L_[k][bi];return v==null?null:`${k.slice(2)}${k[0]==='S'?'(SDM)':''} ${v}`;}).filter(Boolean);
    if(lines.length)h+='<br/>適合度：'+lines.slice(0,8).join('、');
  } else h+='<br/>此處無有效衛星數值(雲/掃描帶外)';
  L.popup().setLatLng(e.latlng).setContent(h).openOn(map);});
document.getElementById('note').innerHTML=
  `合成日期窗：${meta.window[0]} ~ ${meta.window[1]}<br/>有效 SST 網格：${meta.n_sst_valid}<br/>`+
  `可建模魚種(SDM)：${(meta.sdm||[]).length} 種｜來源：${meta.source}`;
document.getElementById('dateHint').innerHTML=
  `衛星合成日期窗：${meta.window[0]} ~ ${meta.window[1]}（早春代表場）。詳細方法與限制請點右上 <b>i</b>。`;
draw();
// 右側圖層面板可收合(點標題列收合；點 i 不收合)
document.getElementById('lpHead').onclick=function(e){if(e.target.closest('#infoBtn'))return;
  document.getElementById('layerPanel').classList.toggle('collapsed');};
// 左側標題面板可收合/重開
var lP=document.getElementById('leftPanel'),lR=document.getElementById('leftReopen');
document.getElementById('leftCollapse').onclick=function(){lP.style.display='none';lR.style.display='flex';};
lR.onclick=function(){lP.style.display='';lR.style.display='none';};
setTimeout(function(){map.invalidateSize();},150);
window.addEventListener('resize',function(){map.invalidateSize();});
__MODALJS__
</script></body></html>
"""

if __name__ == "__main__":
    main()
