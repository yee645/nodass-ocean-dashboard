"""漁場棲地平台：把「現在(浮標)/過去(高解析衛星)/未來(CWA預報)」三個棲地頁
整合為單一入口，以時段切換載入對應子頁(功能零退化)，作為漁民出航前的參考平台。

版型參考中央氣象署海象資訊平台(ocean.cwa.gov.tw)：全螢幕子頁 + 左側可收合面板(標題/導覽/時段)。
定位：環境與漁場潛勢之決策「參考」——安全以中央氣象署官方海象/漁業氣象、海巡警報為準；
漁場為有信心標示的棲地潛勢，非漁獲保證。
產生：dashboard/platform.html(以 iframe 載入 fishing/hires/forecast.html)。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from dashboard_common import INFO_MODAL_JS, SHARED_CSS, info_modal, nav_html

OUT = Path(__file__).resolve().parent / "dashboard" / "platform.html"

MODAL_BODY = """
  <div class="note">
  <b>平台定位</b>：本平台整合「現在(即時浮標)、過去(高解析衛星＋資料驅動 SDM)、未來(中央氣象署 OCM 預報)」三種視角，
  供漁民出航前綜覽海象、海溫鋒面、葉綠素與多魚種棲地潛勢、制定航道與作業計畫之<b>參考</b>。<br/><br/>
  <b>可靠度</b>：海象與環境資訊可作參考(出海安全仍以中央氣象署海象/漁業氣象、海巡警報為準)；
  魚群為<b>環境棲地潛勢</b>(非漁獲保證)，各頁標示驗證 AUC 與資料來源。<br/>
  <b>資料來源</b>：NODASS 開放浮標/衛星影像、中央氣象署 OCM 海流模式、TFRIN 漁場環境、TaiBIF/GBIF 物種出現。對齊 SDG 14。
  </div>
"""

HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant" class="cwa"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NODASS 漁場棲地平台（過去·現在·未來）</title>
<style>__CSS__
  html.cwa .stage > iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:#0e1726;}
  .lp-seg{display:flex;flex-direction:column;gap:6px;padding:4px 12px 0;}
  .lp-seg button{background:#1c2c46;color:#cdd9e5;border:1px solid #2f456b;border-radius:8px;
    padding:8px 12px;font-size:0.85rem;cursor:pointer;text-align:left;}
  .lp-seg button:hover{color:#fff;}
  .lp-seg button.on{background:#2f6fed;color:#fff;border-color:#2f6fed;font-weight:600;}
  .modehint{font-size:0.76rem;color:#9fb3c8;padding:6px 12px 0;line-height:1.5;}
</style></head><body>
<button class="panel-reopen" id="leftReopen" title="開啟資訊" aria-label="開啟資訊">&#9776;</button>
<div class="leftpanel" id="leftPanel">
  <div class="lpane-head">
    <div class="lpane-title">NODASS 漁場棲地平台（過去 · 現在 · 未來）</div>
    <button class="infobtn" id="infoBtn" title="說明" aria-label="說明">i</button>
    <button class="lpane-x" id="leftCollapse" title="收合" aria-label="收合">&times;</button>
  </div>
  <div class="lpane-sub">出航前參考：在過去/現在/未來之間切換，綜覽海象、環境與多魚種棲地潛勢｜產生 __TS__</div>
  __NAV__
  <div class="lp-label" style="padding:8px 12px 0;">時段</div>
  <div class="lp-seg" id="seg"></div>
  <div class="modehint" id="hint"></div>
</div>
<div class="stage">
  <iframe id="pf" title="漁場棲地"></iframe>
</div>
__MODAL__
<script>
const MODES=[
  ['hires.html','過去 · 高解析衛星','衛星 ~4km 海溫/葉綠素/鋒面與資料驅動 SDM（空間交叉驗證 AUC）'],
  ['fishing.html','現在 · 即時浮標','即時浮標海溫與魚種棲地、魚群熱區與漂移、近兩日時間軸回放'],
  ['forecast.html','未來 · CWA 預報','氣象署 OCM 未來數日海象(風/流/潮)+葉綠素，多魚種棲地與信心圖層'],
];
const seg=document.getElementById('seg'), pf=document.getElementById('pf'), hint=document.getElementById('hint');
const VER='__VER__';   // 以建置時間為版本，避免部署後子頁被瀏覽器快取成舊版(GitHub Pages)
function setMode(i){pf.src=MODES[i][0]+'?v='+VER; hint.textContent=MODES[i][2];
  [...seg.children].forEach((c,j)=>c.classList.toggle('on',j===i));}
MODES.forEach(([src,label],i)=>{const b=document.createElement('button');b.textContent=label;
  b.onclick=()=>setMode(i); seg.appendChild(b);});
setMode(1);   // 預設「現在」

// P1.5 跨時段魚種同步：保存各子頁回報的魚種選擇，切換時段後推送給新載入的子頁
let sharedSpecies=[];
window.addEventListener('message',e=>{const d=e.data||{}; if(d.nsp!=='fishsync')return;
  if(d.type==='changed')sharedSpecies=Array.isArray(d.names)?d.names:[];
  if(d.type==='ready')pushSpecies();});
function pushSpecies(){try{pf.contentWindow.postMessage(
  {nsp:'fishsync',type:'apply',names:sharedSpecies},'*');}catch(e){}}

// 左側面板可收合/重開
var lP=document.getElementById('leftPanel'),lR=document.getElementById('leftReopen');
document.getElementById('leftCollapse').onclick=function(){lP.style.display='none';lR.style.display='flex';};
lR.onclick=function(){lP.style.display='';lR.style.display='none';};
__MODALJS__
</script>
</body></html>
"""


def main():
    now = dt.datetime.now()
    html = (HTML.replace("__CSS__", SHARED_CSS)
                .replace("__NAV__", nav_html("platform"))
                .replace("__MODAL__", info_modal("關於本平台", MODAL_BODY))
                .replace("__MODALJS__", INFO_MODAL_JS)
                .replace("__VER__", now.strftime("%Y%m%d%H%M"))
                .replace("__TS__", now.strftime("%Y-%m-%d %H:%M")))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
