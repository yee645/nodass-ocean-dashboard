"""解析 NODASS 開放資料「全臺縣市漁港分布圖」shapefile → sdm/ports.json（航線規劃起點）。

來源：農業部漁業署「全臺縣市漁港分布圖」(NODASS 開放資料，WGS84 經緯度，UTF-8)。
資料夾：35_全臺縣市漁港分布圖/漁港位置圖SHP/漁港位置圖SHP.dbf
僅用 Python 標準庫解析 .dbf 屬性(含 XPOS/YPOS 經緯度)，不需 pyshp/geopandas。
輸出 sdm/ports.json：[{name, kind, county, lat, lon}]，已排除「廢止」漁港。
此檔為航線規劃(第二層)起點清單；前端做起點下拉或地圖吸附最近港。
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

BASE = Path(__file__).resolve().parent
DBF = BASE / "35_全臺縣市漁港分布圖" / "漁港位置圖SHP" / "漁港位置圖SHP.dbf"
OUT = BASE / "sdm" / "ports.json"


def read_dbf(path: Path) -> list[dict[str, str]]:
    """讀 dBASE(.dbf) 為 list[dict]，文字欄以 UTF-8 解碼(對應 .cpg)。"""
    buf = path.read_bytes()
    n_rec = struct.unpack("<I", buf[4:8])[0]
    header_size = struct.unpack("<H", buf[8:10])[0]
    record_size = struct.unpack("<H", buf[10:12])[0]

    # 欄位描述子：自 byte 32 起，每 32 bytes，直到 0x0D 結束
    fields: list[tuple[str, int, int]] = []   # (name, offset_in_record, length)
    p, offset = 32, 1                          # record 第 0 byte 為刪除旗標
    while buf[p] != 0x0D:
        name = buf[p:p + 11].split(b"\x00")[0].decode("utf-8", "replace")
        length = buf[p + 16]
        fields.append((name, offset, length))
        offset += length
        p += 32

    rows: list[dict[str, str]] = []
    base = header_size
    for i in range(n_rec):
        rec = buf[base + i * record_size: base + (i + 1) * record_size]
        if not rec or rec[0:1] == b"*":       # 已刪除紀錄
            continue
        row = {}
        for name, off, length in fields:
            row[name] = rec[off:off + length].decode("utf-8", "replace").strip()
        rows.append(row)
    return rows


def main() -> None:
    if not DBF.exists():
        print(f"找不到漁港 shapefile：{DBF}")
        return
    rows = read_dbf(DBF)
    ports = []
    for r in rows:
        kind = r.get("KIND", "")
        if "廢" in kind:                        # 排除廢止漁港
            continue
        try:
            lon = float(r["XPOS"]); lat = float(r["YPOS"])
        except (KeyError, ValueError):
            continue
        if not (118.0 <= lon <= 123.0 and 21.0 <= lat <= 27.0):
            continue                            # 範圍外/異常座標
        ports.append({
            "name": r.get("NAME", ""), "kind": kind,
            "county": r.get("COUNTY", ""),
            "lat": round(lat, 5), "lon": round(lon, 5),
        })
    ports.sort(key=lambda p: (p["county"], p["name"]))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(ports, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    kinds = sorted({p["kind"] for p in ports})
    print(f"輸出 {len(ports)} 個漁港 -> {OUT.relative_to(BASE)}　分類={kinds}")


if __name__ == "__main__":
    main()
