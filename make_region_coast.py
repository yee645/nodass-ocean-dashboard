"""由 Natural Earth 50m 陸地資料裁切出台灣周邊區域（含中國東南沿海、呂宋北端），
簡化後輸出精簡的 region_coast.json，供儀表板內嵌：陸地遮罩與底圖自繪共用。

只在更新海岸線來源時手動執行一次；產物 region_coast.json 已納入版控。
"""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path(__file__).with_name("_ne_50m_land.geojson")
OUT = Path(__file__).with_name("region_coast.json")

# 裁切範圍 (minlon, minlat, maxlon, maxlat)：涵蓋網格與地圖可視範圍
BBOX = (114.0, 18.0, 124.5, 28.0)
EPS = 0.012  # 簡化容差（度）


def inter_x(a, b, x):
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def inter_y(a, b, y):
    t = (y - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), y)


def _clip_edge(pts, inside, intersect):
    out = []
    n = len(pts)
    for i in range(n):
        cur, prev = pts[i], pts[i - 1]
        ci, pi = inside(cur), inside(prev)
        if ci:
            if not pi:
                out.append(intersect(prev, cur))
            out.append(cur)
        elif pi:
            out.append(intersect(prev, cur))
    return out


def clip_to_bbox(ring):
    """Sutherland–Hodgman 將多邊形環裁切到 BBOX（矩形為凸區，結果正確）。"""
    minx, miny, maxx, maxy = BBOX
    pts = ring
    pts = _clip_edge(pts, lambda p: p[0] >= minx, lambda a, b: inter_x(a, b, minx))
    if not pts:
        return []
    pts = _clip_edge(pts, lambda p: p[0] <= maxx, lambda a, b: inter_x(a, b, maxx))
    if not pts:
        return []
    pts = _clip_edge(pts, lambda p: p[1] >= miny, lambda a, b: inter_y(a, b, miny))
    if not pts:
        return []
    pts = _clip_edge(pts, lambda p: p[1] <= maxy, lambda a, b: inter_y(a, b, maxy))
    return pts


def _perp(p, a, b):
    if a == b:
        return ((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2) ** 0.5
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = a[0] + t * dx, a[1] + t * dy
    return ((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5


def simplify(pts, eps):
    if len(pts) < 3:
        return pts
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = _perp(pts[i], pts[0], pts[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        left = simplify(pts[:idx + 1], eps)
        right = simplify(pts[idx:], eps)
        return left[:-1] + right
    return [pts[0], pts[-1]]


def iter_rings(geom):
    t, c = geom.get("type"), geom.get("coordinates") or []
    if t == "Polygon":
        for ring in c:
            yield ring
    elif t == "MultiPolygon":
        for poly in c:
            for ring in poly:
                yield ring


def main():
    gj = json.loads(SRC.read_text(encoding="utf-8"))
    feats = []
    for feat in gj.get("features", []):
        for ring in iter_rings(feat.get("geometry") or {}):
            # 跳過台灣本島與鄰近離島（lon 119.8–122.2, lat 21.5–25.4），改用 taiwan_coast.json 精細版
            lons = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            if 119.8 <= min(lons) and max(lons) <= 122.2 \
                    and 21.5 <= min(lats) and max(lats) <= 25.4:
                continue
            pts = [(round(p[0], 4), round(p[1], 4)) for p in ring]
            clipped = clip_to_bbox(pts)
            if len(clipped) < 4:
                continue
            simp = simplify(clipped, EPS)
            simp = [[round(x, 3), round(y, 3)] for x, y in simp]
            if len(simp) < 4:
                continue
            if simp[0] != simp[-1]:
                simp.append(simp[0])
            feats.append({"type": "Feature", "properties": {},
                          "geometry": {"type": "Polygon", "coordinates": [simp]}})

    # 併入 taiwan_coast.json 的精細台灣＋澎湖＋離島輪廓（Natural Earth 50m 缺澎湖且本島較粗）
    tw_file = Path(__file__).with_name("taiwan_coast.json")
    if tw_file.exists():
        tw = json.loads(tw_file.read_text(encoding="utf-8"))
        for feat in tw.get("features", []):
            for ring in iter_rings(feat.get("geometry") or {}):
                simp = [[round(p[0], 3), round(p[1], 3)] for p in ring]
                if len(simp) < 4:
                    continue
                if simp[0] != simp[-1]:
                    simp.append(simp[0])
                feats.append({"type": "Feature", "properties": {},
                              "geometry": {"type": "Polygon", "coordinates": [simp]}})

    out = {"type": "FeatureCollection", "features": feats}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    npts = sum(len(f["geometry"]["coordinates"][0]) for f in feats)
    print(f"已產生 {OUT}  多邊形={len(feats)}  總點數={npts}  大小={OUT.stat().st_size}B")


if __name__ == "__main__":
    main()
