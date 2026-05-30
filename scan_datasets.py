"""掃描 NODASS 資料集 JSON，依四個競賽題目過濾並輸出彙整。"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path(r"D:\nodass")
NORMAL = DATA_DIR / "datasets.json"
MARINE = DATA_DIR / "datasets_marine.json"
REPORT = DATA_DIR / "scan_report.txt"

# 重新導向 stdout 至 UTF-8 檔案，避免 Windows 本機編碼亂碼
_buf = io.StringIO()
sys.stdout = _buf


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_any(text: str, keywords: list[str]) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in keywords)


def summarize(items: list[dict]) -> None:
    cats = Counter(i.get("DataCategory", "?") for i in items)
    sources = Counter(i.get("CollectSource", "?") for i in items)
    pubs = Counter(i.get("publisherOID", "?") for i in items)
    print("  類別:", dict(cats))
    print("  來源:", dict(sources))
    print("  單位:", dict(pubs))


def print_row(it: dict, idx: int) -> None:
    apilink = it.get("APILink") or "-"
    gis = it.get("RedirectToGISUrl") or "-"
    dlt = it.get("DownloadType") or "-"
    desc = (it.get("description") or "").replace("\n", " ")[:90]
    print(
        f"  [{idx:>2}] id={it['MetaDataID']:<3} "
        f"類={it.get('DataCategory'):<8} 來={it.get('CollectSource'):<6} "
        f"屬={it.get('categoryDataset'):<6} 下載={dlt:<6} "
        f"單位={it.get('publisherOID'):<12} "
        f"\n        子項：{it.get('item')}"
        f"\n        說明：{desc}"
        f"\n        API ：{apilink}"
        f"\n        GIS ：{gis}"
    )


def main() -> None:
    normal = load(NORMAL)
    marine = load(MARINE)
    print(f"正規化資料：{len(normal)} 筆；其他涉海資料：{len(marine)} 筆")
    print("=" * 80)
    print("正規化資料總覽：")
    summarize(normal)
    print("=" * 80)
    print("涉海資料總覽：")
    summarize(marine)
    print("=" * 80)

    topics: dict[str, list[str]] = {
        "T0_魚群/SST/葉綠素/鹽度": [
            "海溫", "鹽度", "葉綠素", "水質", "生物", "魚",
            "sst", "chlorophyll", "fish",
        ],
        "T1_離岸風電/鯨豚/水下聲景": [
            "聲景", "聲音", "鯨", "豚", "海豚", "海洋哺乳", "風電",
            "風機", "風場", "noise", "soundscape", "cetacean", "wind",
        ],
        "T2_海漂垃圾/HFR海流/風場": [
            "海流", "風", "漂", "垃圾", "廢棄", "hfr",
            "current", "debris", "trash",
        ],
        "T3_瘋狗浪/波浪浮標/潮位": [
            "波浪", "波高", "湧浪", "浮標", "潮位",
            "wave", "buoy", "tide",
        ],
    }

    indexed: dict[str, list[dict]] = defaultdict(list)
    for it in normal + marine:
        haystack = " ".join(
            str(it.get(k, "") or "")
            for k in ("Grouping", "DataCategory", "item", "description")
        )
        for topic, kws in topics.items():
            if has_any(haystack, kws):
                indexed[topic].append(it)

    for topic in topics:
        items = indexed.get(topic, [])
        print(f"\n{topic}：命中 {len(items)} 筆")
        print("-" * 80)
        for i, it in enumerate(items):
            print_row(it, i + 1)
            print()


if __name__ == "__main__":
    main()
    sys.stdout = sys.__stdout__
    REPORT.write_text(_buf.getvalue(), encoding="utf-8")
    print(f"written: {REPORT}  bytes={REPORT.stat().st_size}")
