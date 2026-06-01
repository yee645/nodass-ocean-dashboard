"""漁場棲地平台：把「現在(浮標)/過去(高解析衛星)/未來(CWA預報)」三個棲地頁
整合為單一入口，以時段切換載入對應子頁(功能零退化)，作為漁民出航前的參考平台。

定位：環境與漁場潛勢之決策「參考」——安全以中央氣象署官方海象/漁業氣象、海巡警報為準；
漁場為有信心標示的棲地潛勢，非漁獲保證。
產生：dashboard/platform.html(以 iframe 載入 fishing/hires/forecast.html)。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from dashboard_common import SHARED_CSS, nav_html

OUT = Path(__file__).resolve().parent / "dashboard" / "platform.html"

HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NODASS 漁場棲地平台（過去·現在·未來）</title>
<style>__CSS__
  .pframe{width:100%;height:clamp(540px,80vh,960px);border:1px solid #24344f;border-radius:8px;
    background:#0e1726;}
  .modehint{font-size:0.82rem;color:#9fb3c8;}
</style></head><body>
<header><h1>NODASS 漁場棲地平台（過去 · 現在 · 未來）</h1>
<div class="sub">出航前參考：在過去/現在/未來之間切換，綜覽海象、環境與多魚種棲地潛勢｜產生 __TS__</div></header>
__NAV__
<div class="ctrl">
  <strong style="color:#cdd9e5;font-size:0.85rem;">時段</strong>
  <span class="seg" id="seg"></span>
  <span class="modehint" id="hint"></span>
</div>
<div style="padding:0 12px 12px;">
  <iframe id="pf" class="pframe" title="漁場棲地"></iframe>
</div>
<div class="wrap"><div class="panel" style="flex:1;"><div class="note">
  <b>平台定位</b>：本平台整合「現在(即時浮標)、過去(高解析衛星＋資料驅動 SDM)、未來(中央氣象署 OCM 預報)」三種視角，
  供漁民出航前綜覽海象、海溫鋒面、葉綠素與多魚種棲地潛勢、制定航道與作業計畫之<b>參考</b>。<br/>
  <b>可靠度</b>：海象與環境資訊可作參考(出海安全仍以中央氣象署海象/漁業氣象、海巡警報為準)；
  魚群為<b>環境棲地潛勢</b>(非漁獲保證)，各頁標示驗證 AUC 與資料來源。<br/>
  <b>資料來源</b>：NODASS 開放浮標/衛星影像、中央氣象署 OCM 海流模式、TFRIN 漁場環境、TaiBIF/GBIF 物種出現。對齊 SDG 14。
</div></div></div>
<script>
const MODES=[
  ['hires.html','過去 · 高解析衛星','衛星 ~4km 海溫/葉綠素/鋒面與資料驅動 SDM（空間交叉驗證 AUC）'],
  ['fishing.html','現在 · 即時浮標','即時浮標海溫與魚種棲地、魚群熱區與漂移、近兩日時間軸回放'],
  ['forecast.html','未來 · CWA 預報','氣象署 OCM 未來數日海溫/海流 + 葉綠素，多魚種棲地與海流向量'],
];
const seg=document.getElementById('seg'), pf=document.getElementById('pf'), hint=document.getElementById('hint');
function setMode(i){pf.src=MODES[i][0]; hint.textContent=MODES[i][2];
  [...seg.children].forEach((c,j)=>c.classList.toggle('on',j===i));}
MODES.forEach(([src,label],i)=>{const b=document.createElement('button');b.textContent=label;
  b.onclick=()=>setMode(i); seg.appendChild(b);});
setMode(1);   // 預設「現在」
</script>
</body></html>
"""


def main():
    html = (HTML.replace("__CSS__", SHARED_CSS)
                .replace("__NAV__", nav_html("platform"))
                .replace("__TS__", dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
