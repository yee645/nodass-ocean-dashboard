import { PolygonLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { BathymetryPayload } from '@/data/useExtras'

// 淺→深：淺色警示、深色安全，跟 RdYlGn 系列的邏輯呼應但不用色相跳動的彩虹色。
const DEPTH_REF = 200 // m，超過此深度視為「深」，不再加深顏色

function depthColor(depth: number): [number, number, number, number] {
  const t = Math.max(0, Math.min(1, depth / DEPTH_REF))
  const r = Math.round(255 * (1 - t) * 0.7)
  const g = Math.round(120 + 100 * t)
  const b = Math.round(180 + 60 * t)
  return [r, g, b, 90]
}

/** 水深參考圖層（第二層航線規劃用，非正式等深線，僅供吃水限制的直覺對照）。 */
export function bathymetryLayer(bathymetry: BathymetryPayload): Layer {
  const half = bathymetry.step / 2
  return new PolygonLayer({
    id: 'bathymetry-depth',
    data: bathymetry.cells,
    getPolygon: (c) => [
      [c.lon - half, c.lat - half],
      [c.lon + half, c.lat - half],
      [c.lon + half, c.lat + half],
      [c.lon - half, c.lat + half],
    ],
    getFillColor: (c) => depthColor(c.depth),
    stroked: false,
    filled: true,
    pickable: false,
  })
}
