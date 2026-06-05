import {
  PolygonLayer,
  ScatterplotLayer,
  PathLayer,
  LineLayer,
  IconLayer,
  TextLayer,
} from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { FishCell, Species, Station } from '@/data/contracts'
import { suit, heat, colorFor, bearingDeg, dirName } from './nowMath'

const HOT_THR = 70
const ccwFromBearing = (b: number): number => (360 - b) % 360

// 藍色漂移箭頭圖示（指北、可染色）。
const DRIFT_SVG =
  "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='14' viewBox='0 0 10 14'><polygon points='5,0 9,13 5,10 1,13' fill='white'/></svg>"
const DRIFT_ICON = {
  url: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(DRIFT_SVG)}`,
  width: 10,
  height: 14,
  anchorX: 5,
  anchorY: 7,
  mask: true,
}

/** 適合度網格（heat 色、opacity 0.5）；僅 v>0 的格子。 */
export function suitabilityGridLayer(
  grid: FishCell[],
  sp: Species,
  month: number,
  step: number,
): Layer {
  const h = step / 2
  const cells = grid
    .map((c) => ({ c, v: suit(c.v, sp, month) }))
    .filter((o) => o.v > 0)
  return new PolygonLayer<{ c: FishCell; v: number }>({
    id: 'gridField-suit',
    data: cells,
    getPolygon: ({ c }) => [
      [c.lon - h, c.lat - h],
      [c.lon + h, c.lat - h],
      [c.lon + h, c.lat + h],
      [c.lon - h, c.lat + h],
    ],
    getFillColor: ({ v }) => {
      const [r, g, b] = heat(v)
      return [r, g, b, 128]
    },
    stroked: false,
    filled: true,
    pickable: false,
    updateTriggers: { getFillColor: [sp.name, month] },
  })
}

/** 浮標站點（半徑/燈號隨值，pickable 供 hover tooltip）。 */
export function stationLayer(stations: Station[], mode: string | null): Layer {
  const valOf = (s: Station): number =>
    mode == null ? s.fish_score : (s.species[mode] ?? 0)
  return new ScatterplotLayer<Station>({
    id: 'buoy-stations',
    data: stations,
    getPosition: (s) => [s.lon, s.lat],
    getRadius: (s) => 5 + valOf(s) / 12,
    radiusUnits: 'pixels',
    getFillColor: (s) => {
      const [r, g, b] = colorFor(valOf(s))
      return [r, g, b, 242]
    },
    getLineColor: [255, 255, 255],
    lineWidthMinPixels: 1.2,
    stroked: true,
    filled: true,
    pickable: true,
    updateTriggers: { getRadius: [mode], getFillColor: [mode] },
  })
}

interface HotCell {
  c: FishCell
  v: number
}

const gkey = (la: number, lo: number, step: number): string =>
  `${Math.round(la / step)}|${Math.round(lo / step)}`

/** 連通分群（4 鄰接）取魚群熱區叢集。 */
function clusters(
  grid: FishCell[],
  sp: Species,
  month: number,
  step: number,
): HotCell[][] {
  const hot: HotCell[] = grid
    .map((c) => ({ c, v: suit(c.v, sp, month) }))
    .filter((o) => o.v >= HOT_THR)
  const byKey = new Map<string, HotCell>()
  hot.forEach((o) => byKey.set(gkey(o.c.lat, o.c.lon, step), o))
  const seen = new Set<string>()
  const out: HotCell[][] = []
  const NB = [
    [step, 0],
    [-step, 0],
    [0, step],
    [0, -step],
  ]
  for (const o of hot) {
    const k0 = gkey(o.c.lat, o.c.lon, step)
    if (seen.has(k0)) continue
    const stack = [o]
    const group: HotCell[] = []
    seen.add(k0)
    while (stack.length) {
      const cur = stack.pop()!
      group.push(cur)
      for (const [dla, dlo] of NB) {
        const nk = gkey(cur.c.lat + dla, cur.c.lon + dlo, step)
        const nb = byKey.get(nk)
        if (nb && !seen.has(nk)) {
          seen.add(nk)
          stack.push(nb)
        }
      }
    }
    out.push(group)
  }
  return out
}

/**
 * 魚群熱區與漂移：聯集填色 + footprint 外框 + 每群單一聚合方向箭頭與標籤。
 * 1:1 移植 build_fishing.py 的 drawMovement。回傳多個圖層（皆排於 drift 層級）。
 */
export function hotZoneLayers(
  grid: FishCell[],
  sp: Species,
  month: number,
  step: number,
): Layer[] {
  const groups = clusters(grid, sp, month, step)
  if (!groups.length) return []
  const h = step / 2

  const fillCells: FishCell[] = []
  const outline: { path: [number, number][] }[] = []
  const driftLines: { from: [number, number]; to: [number, number] }[] = []
  const arrows: { position: [number, number]; angle: number }[] = []
  const labels: { position: [number, number]; text: string }[] = []

  for (const group of groups) {
    const keys = new Set(group.map((o) => gkey(o.c.lat, o.c.lon, step)))
    for (const { c } of group) {
      fillCells.push(c)
      // footprint 外框：只畫未與同群相鄰的格邊
      if (!keys.has(gkey(c.lat + step, c.lon, step)))
        outline.push({
          path: [
            [c.lon - h, c.lat + h],
            [c.lon + h, c.lat + h],
          ],
        })
      if (!keys.has(gkey(c.lat - step, c.lon, step)))
        outline.push({
          path: [
            [c.lon - h, c.lat - h],
            [c.lon + h, c.lat - h],
          ],
        })
      if (!keys.has(gkey(c.lat, c.lon + step, step)))
        outline.push({
          path: [
            [c.lon + h, c.lat - h],
            [c.lon + h, c.lat + h],
          ],
        })
      if (!keys.has(gkey(c.lat, c.lon - step, step)))
        outline.push({
          path: [
            [c.lon - h, c.lat - h],
            [c.lon - h, c.lat + h],
          ],
        })
    }
    // 聚合方向（群內各格海流平均）與群質心
    const uv = group.filter((o) => o.c.u !== undefined)
    let mu = 0
    let mw = 0
    uv.forEach((o) => {
      mu += o.c.u!
      mw += o.c.w!
    })
    const hasUv = uv.length > 0
    if (hasUv) {
      mu /= uv.length
      mw /= uv.length
    }
    const spd = hasUv ? Math.hypot(mu, mw) : null
    const deg = spd != null ? bearingDeg(mu, mw) : null
    const dir = deg != null ? dirName(deg) : null
    const clat = group.reduce((a, o) => a + o.c.lat, 0) / group.length
    const clon = group.reduce((a, o) => a + o.c.lon, 0) / group.length
    labels.push({
      position: [clon, clat],
      text: `魚群熱區${dir ? '·往' + dir : ''}`,
    })
    if (spd != null && spd > 0.001 && deg != null) {
      const sc = 0.9
      const lat2 = clat + mw * sc
      const lon2 = clon + mu * sc
      driftLines.push({ from: [clon, clat], to: [lon2, lat2] })
      arrows.push({ position: [lon2, lat2], angle: ccwFromBearing(deg) })
    }
  }

  const layers: Layer[] = [
    new PolygonLayer<FishCell>({
      id: 'drift-fill',
      data: fillCells,
      getPolygon: (c) => [
        [c.lon - h, c.lat - h],
        [c.lon + h, c.lat - h],
        [c.lon + h, c.lat + h],
        [c.lon - h, c.lat + h],
      ],
      getFillColor: [255, 208, 0, 46], // #ffd000 @0.18
      stroked: false,
      filled: true,
      pickable: false,
      updateTriggers: { getPolygon: [sp.name, month] },
    }),
    new PathLayer<{ path: [number, number][] }>({
      id: 'drift-outline',
      data: outline,
      getPath: (d) => d.path,
      getColor: [255, 208, 0, 230],
      getWidth: 2,
      widthUnits: 'pixels',
      pickable: false,
      updateTriggers: { getPath: [sp.name, month] },
    }),
    new LineLayer<{ from: [number, number]; to: [number, number] }>({
      id: 'drift-line',
      data: driftLines,
      getSourcePosition: (d) => d.from,
      getTargetPosition: (d) => d.to,
      getColor: [127, 212, 255, 242],
      getWidth: 2.5,
      widthUnits: 'pixels',
      pickable: false,
    }),
    new IconLayer<{ position: [number, number]; angle: number }>({
      id: 'drift-arrow',
      data: arrows,
      getIcon: () => DRIFT_ICON,
      getPosition: (d) => d.position,
      getAngle: (d) => d.angle,
      getSize: 16,
      getColor: [127, 212, 255],
      sizeUnits: 'pixels',
      pickable: false,
    }),
    new TextLayer<{ position: [number, number]; text: string }>({
      id: 'drift-label',
      data: labels,
      getPosition: (d) => d.position,
      getText: (d) => d.text,
      getColor: [255, 208, 0],
      getSize: 11,
      sizeUnits: 'pixels',
      getPixelOffset: [0, -14],
      fontFamily: "'Microsoft JhengHei', 'Segoe UI', sans-serif",
      characterSet: 'auto', // 由資料自動建字元圖集，涵蓋中文標籤
      outlineColor: [0, 0, 0, 255],
      outlineWidth: 2,
      fontSettings: { sdf: true },
      pickable: false,
    }),
  ]
  return layers
}
