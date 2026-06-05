import { PolygonLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import { PALETTE, jet, type PaletteName } from '../palettes'
import { LOWCONF } from './fieldConfig'
import type { HiresPayload } from '@/data/contracts'

/** hires base 欄位（sst 值域與 forecast 不同：18–28）。 */
const HIRES_CFG: Record<
  string,
  { lo: number; hi: number; log: boolean; pal: PaletteName; label: string }
> = {
  sst: { lo: 18, hi: 28, log: false, pal: 'jet', label: '海溫 SST (°C)' },
  chl: { lo: -1.3, hi: 0.5, log: true, pal: 'jet', label: '葉綠素 (mg/m³)' },
  front: { lo: 0, hi: 1.2, log: false, pal: 'jet', label: '海溫鋒面強度' },
  conf: { lo: 0, hi: 1, log: false, pal: 'conf', label: '資料信心(出現點支持)' },
}

interface HiresArgs {
  lat: number[]
  lon: number[]
  layers: HiresPayload['layers']
  step: number
  baseField: string
  speciesKeys: string[]
  confDim: boolean
}

type RGBA = [number, number, number, number]
const TRANSPARENT: RGBA = [0, 0, 0, 0]

/** hires 純量場（移植 build_hires.py 的 draw/drawHabitat）。 */
export function hiresGridLayer(a: HiresArgs): Layer | null {
  const { lat, lon, layers, step, baseField, speciesKeys, confDim } = a
  const h = step / 2
  const conf = layers.conf ?? null
  const N = lat.length

  const cellOpacity = (i: number): number => {
    if (!confDim || !conf) return 0.5
    const c = conf[i]
    return c == null || c < LOWCONF ? 0.12 : 0.5
  }

  const colorAt = (i: number): RGBA => {
    if (baseField === 'habitat') {
      let best: number | null = null
      for (const k of speciesKeys) {
        const v = layers[k]?.[i]
        if (v != null && (best == null || v > best)) best = v
      }
      if (best == null) return TRANSPARENT
      const [r, g, b] = jet(best / 100)
      return [r, g, b, Math.round(cellOpacity(i) * 255)]
    }
    const cfg = HIRES_CFG[baseField]
    if (!cfg) return TRANSPARENT
    const v = layers[baseField]?.[i]
    if (v == null) return TRANSPARENT
    const t = cfg.log
      ? (Math.log10(Math.max(0.01, v)) - cfg.lo) / (cfg.hi - cfg.lo)
      : (v - cfg.lo) / (cfg.hi - cfg.lo)
    const [r, g, b] = PALETTE[cfg.pal](t)
    const alpha = baseField === 'conf' ? 0.58 : cellOpacity(i)
    return [r, g, b, Math.round(alpha * 255)]
  }

  const idx = Array.from({ length: N }, (_, i) => i)
  return new PolygonLayer<number>({
    id: `gridField-${baseField}`,
    data: idx,
    getPolygon: (i) => [
      [lon[i] - h, lat[i] - h],
      [lon[i] + h, lat[i] - h],
      [lon[i] + h, lat[i] + h],
      [lon[i] - h, lat[i] + h],
    ],
    getFillColor: (i) => colorAt(i),
    stroked: false,
    filled: true,
    pickable: false,
    updateTriggers: {
      getFillColor: [baseField, speciesKeys.join(','), confDim],
    },
  })
}
