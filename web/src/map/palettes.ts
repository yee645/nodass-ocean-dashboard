/**
 * 配色：1:1 移植自 build_forecast.py 內嵌 JS（jet / 蒲福風級 / 潮位發散 / 信心 RdYlGn）。
 * deck.gl 色彩存取子需 [r,g,b]（0–255）；另提供 CSS gradient 供圖例使用。
 */

export type RGB = [number, number, number]
type Stop = [number, string]

function hx(h: string): RGB {
  return [
    parseInt(h.slice(1, 3), 16),
    parseInt(h.slice(3, 5), 16),
    parseInt(h.slice(5, 7), 16),
  ]
}

function clamp01(t: number): number {
  return Math.max(0, Math.min(1, t))
}

/** 多色階線性內插（對應舊 stops()）。 */
function stops(arr: Stop[], t: number): RGB {
  t = clamp01(t)
  for (let i = 1; i < arr.length; i++) {
    if (t <= arr[i][0]) {
      const a = arr[i - 1]
      const b = arr[i]
      const f = (t - a[0]) / (b[0] - a[0] || 1)
      const c1 = hx(a[1])
      const c2 = hx(b[1])
      return [
        (c1[0] + (c2[0] - c1[0]) * f) | 0,
        (c1[1] + (c2[1] - c1[1]) * f) | 0,
        (c1[2] + (c2[2] - c1[2]) * f) | 0,
      ]
    }
  }
  return hx(arr[arr.length - 1][1])
}

/** jet 色階（對應舊 jet()）。 */
export function jet(t: number): RGB {
  t = clamp01(t)
  const r = clamp01(1.5 - Math.abs(4 * t - 3))
  const g = clamp01(1.5 - Math.abs(4 * t - 2))
  const b = clamp01(1.5 - Math.abs(4 * t - 1))
  return [(r * 255) | 0, (g * 255) | 0, (b * 255) | 0]
}

// 風速採近中央氣象署蒲福風級配色；潮位採發散色階(低潮藍-高潮紅)；信心採 RdYlGn。
const WINDPAL: Stop[] = [
  [0, '#2c7fb8'],
  [0.18, '#41b6c4'],
  [0.36, '#a1dab4'],
  [0.5, '#ffffb2'],
  [0.66, '#fecc5c'],
  [0.82, '#f03b20'],
  [1, '#7a0177'],
]
const TIDEPAL: Stop[] = [
  [0, '#2166ac'],
  [0.5, '#f2f4f7'],
  [1, '#b2182b'],
]
const CONFPAL: Stop[] = [
  [0, '#d73027'],
  [0.25, '#fc8d59'],
  [0.5, '#fee08b'],
  [0.75, '#d9ef8b'],
  [1, '#1a9850'],
]

export const wind = (t: number): RGB => stops(WINDPAL, t)
export const tide = (t: number): RGB => stops(TIDEPAL, t)
export const conf = (t: number): RGB => stops(CONFPAL, t)

export type PaletteName = 'jet' | 'wind' | 'tide' | 'conf'

export const PALETTE: Record<PaletteName, (t: number) => RGB> = {
  jet,
  wind,
  tide,
  conf,
}

/** 圖例用 CSS 線性漸層（對應舊 gradCss()）。 */
export function gradientCss(name: PaletteName): string {
  const f = PALETTE[name]
  const seg: string[] = []
  for (let i = 0; i <= 10; i++) {
    const [r, g, b] = f(i / 10)
    seg.push(`rgb(${r},${g},${b}) ${i * 10}%`)
  }
  return `linear-gradient(90deg,${seg.join(',')})`
}

/** 蒲福風級（對應舊 beaufort()）。 */
export function beaufort(ms: number): number {
  const b = [0.3, 1.6, 3.4, 5.5, 8, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]
  let f = 0
  for (let i = 0; i < b.length; i++) if (ms >= b[i]) f = i + 1
  return f
}
