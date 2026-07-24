import { PolygonLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { DepthBand } from '@/data/useExtras'

// 淺→深：淺色警示、深色安全，跟 RdYlGn 系列的邏輯呼應但不用色相跳動的彩虹色。
const DEPTH_REF = 200 // m，超過此深度視為「深」，不再加深顏色

function depthColor(depth: number): [number, number, number, number] {
  const t = Math.max(0, Math.min(1, depth / DEPTH_REF))
  const r = Math.round(255 * (1 - t) * 0.7)
  const g = Math.round(120 + 100 * t)
  const b = Math.round(180 + 60 * t)
  return [r, g, b, 90]
}

/** 水深分級圖層（第二層航線規劃用，PyQGIS 對 GEBCO 分級+polygonize 匯出的等深帶，非正式航行圖）。 */
export function bathymetryLayer(bands: DepthBand[]): Layer {
  return new PolygonLayer({
    id: 'bathymetry-depth',
    data: bands,
    getPolygon: (b) => b.polygon,
    getFillColor: (b) => depthColor((b.minDepth + b.maxDepth) / 2),
    stroked: false,
    filled: true,
    pickable: false,
  })
}
