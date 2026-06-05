import type { Layer } from '@deck.gl/core'

/**
 * 固定圖層堆疊順序（取代 Leaflet pane）。deck.gl 以陣列順序即 z-order，
 * 永遠依此權威順序排列，從機制上杜絕堆疊衝突。
 * 索引小者在下、大者在上。
 */
export const LAYER_ORDER = [
  'landMask', // 陸地遮罩(最底)
  'gridField', // 純量場(互斥 base：SST/海流速/風/潮/信心/葉綠素/棲地)
  'currentVector', // 海流向量(可混用 overlay)
  'windVector', // 風向量(可混用 overlay)
  'drift', // 魚群漂移/熱區(可混用)
  'occurrence', // 物種出現點(可混用)
  'buoy', // 浮標站點(可混用，最上)
] as const

export type LayerId = (typeof LAYER_ORDER)[number]

const RANK: Record<string, number> = Object.fromEntries(
  LAYER_ORDER.map((id, i) => [id, i]),
)

/**
 * 依 LAYER_ORDER 排序 deck.gl 圖層、濾除 null。
 * 圖層 id 需以 LayerId 為前綴（例 'gridField-sst'），未知 id 排到最後。
 */
export function orderLayers(layers: (Layer | null | false)[]): Layer[] {
  const valid = layers.filter((l): l is Layer => Boolean(l))
  const rankOf = (l: Layer): number => {
    const id = String(l.id)
    const base = id.includes('-') ? id.slice(0, id.indexOf('-')) : id
    return RANK[base] ?? LAYER_ORDER.length
  }
  return valid.slice().sort((a, b) => rankOf(a) - rankOf(b))
}
