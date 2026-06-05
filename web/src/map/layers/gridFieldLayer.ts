import { PolygonLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import { PALETTE, jet } from '../palettes'
import { FIELD_CFG, LOWCONF } from './fieldConfig'
import type { BaseField } from '@/store/useAppStore'
import type { Cell, LeadData } from '@/data/contracts'

export interface GridArgs {
  cells: Cell[]
  step: number
  baseField: BaseField
  lead: LeadData
  leadKey: string
  chl: (number | null)[]
  conf: (number | null)[]
  species: string[]
  confDim: boolean
}

type RGBA = [number, number, number, number]
const TRANSPARENT: RGBA = [0, 0, 0, 0]

/**
 * 純量場格點圖層（互斥 base）。1:1 移植 build_forecast.py 的 draw/drawHabitat：
 * 色階、log 縮放、動態相對色階(ws)、棲地多魚種取最大、低信心淡化。
 */
export function gridFieldLayer(a: GridArgs): Layer {
  const { cells, step, baseField, lead, chl, conf, species, confDim } = a
  const h = step / 2
  const cfg = FIELD_CFG[baseField]

  // 選定要上色的陣列（habitat 為逐魚種、另行處理）。
  const fieldArr: (number | null)[] | null =
    baseField === 'habitat'
      ? null
      : baseField === 'chl'
        ? chl
        : baseField === 'conf'
          ? conf
          : (lead as unknown as Record<string, (number | null)[]>)[baseField]

  // 動態色階（ws：lo/hi 為 null 時依當前資料縮放）。
  let lo = cfg.lo
  let hi = cfg.hi
  if ((lo == null || hi == null) && fieldArr) {
    let mn = Infinity
    let mx = -Infinity
    for (const v of fieldArr) {
      if (v == null) continue
      if (v < mn) mn = v
      if (v > mx) mx = v
    }
    lo = mn
    hi = mx > mn ? mx : mn + 1
  }
  const LO = lo ?? 0
  const HI = hi ?? 1

  // 低信心淡化（對應舊 cellOpacity）。
  const cellOpacity = (i: number): number => {
    if (!confDim) return 0.5
    const c = conf[i]
    return c == null || c < LOWCONF ? 0.12 : 0.5
  }

  const colorAt = (i: number): RGBA => {
    if (baseField === 'habitat') {
      let best: number | null = null
      for (const nm of species) {
        const arr = lead.s[nm]
        if (!arr) continue
        const v = arr[i]
        if (v != null && (best == null || v > best)) best = v
      }
      if (best == null) return TRANSPARENT
      const [r, g, b] = jet(best / 100)
      return [r, g, b, Math.round(cellOpacity(i) * 255)]
    }
    const v = fieldArr![i]
    if (v == null) return TRANSPARENT
    const t = cfg.log
      ? (Math.log10(Math.max(0.01, v)) - LO) / (HI - LO)
      : (v - LO) / (HI - LO)
    const [r, g, b] = PALETTE[cfg.pal](t)
    const alpha = baseField === 'conf' ? 0.58 : cellOpacity(i)
    return [r, g, b, Math.round(alpha * 255)]
  }

  return new PolygonLayer<Cell>({
    id: `gridField-${baseField}`,
    data: cells,
    getPolygon: (c) => [
      [c.lon - h, c.lat - h],
      [c.lon + h, c.lat - h],
      [c.lon + h, c.lat + h],
      [c.lon - h, c.lat + h],
    ],
    getFillColor: (_c, info) => colorAt(info.index),
    stroked: false,
    filled: true,
    pickable: false,
    updateTriggers: {
      // 任一影響上色的輸入變動都強制重算（id 跨 lead/魚種相同需此觸發）。
      getFillColor: [baseField, a.leadKey, species.join(','), confDim, LO, HI],
    },
  })
}
