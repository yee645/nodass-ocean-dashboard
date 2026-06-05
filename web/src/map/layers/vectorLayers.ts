import { IconLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { Cell, LeadData } from '@/data/contracts'

// 向上(指北)的白色箭頭；mask:true 讓 getColor 染色。viewBox 10x14、錨點置中。
const ARROW_SVG =
  "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='14' viewBox='0 0 10 14'><polygon points='5,0 9,13 5,10 1,13' fill='white'/></svg>"
const ARROW_URL = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(ARROW_SVG)}`
const ICON = {
  url: ARROW_URL,
  width: 10,
  height: 14,
  anchorX: 5,
  anchorY: 7,
  mask: true,
}

interface Arrow {
  position: [number, number]
  angle: number
  size: number
}

const STRIDE = 7 // 抽稀：每 7 格取一支，對應舊 i+=7
const CURRENT_COLOR: [number, number, number] = [207, 232, 255] // #cfe8ff
const WIND_COLOR: [number, number, number] = [255, 210, 127] // #ffd27f

// deck IconLayer 的 getAngle 為逆時針角度，圖示朝北(0)；
// 羅盤方位(順時針)轉為 (360 - bearing) % 360。
const ccwFromBearing = (bearing: number): number => (360 - bearing) % 360

/** 海流向量（對應舊 curArrows）。 */
export function currentVectorLayer(
  cells: Cell[],
  lead: LeadData,
  leadKey: string,
): Layer {
  const arrows: Arrow[] = []
  for (let i = 0; i < cells.length; i += STRIDE) {
    const u = lead.u[i]
    const w = lead.w[i]
    if (u == null || w == null) continue
    if (Math.hypot(u, w) < 0.05) continue
    const bearing = (Math.atan2(u, w) * 180) / Math.PI
    arrows.push({
      position: [cells[i].lon, cells[i].lat],
      angle: ccwFromBearing((bearing + 360) % 360),
      size: 16,
    })
  }
  return new IconLayer<Arrow>({
    id: `currentVector-${leadKey}`,
    data: arrows,
    getIcon: () => ICON,
    getPosition: (d) => d.position,
    getAngle: (d) => d.angle,
    getSize: (d) => d.size,
    getColor: CURRENT_COLOR,
    sizeUnits: 'pixels',
    pickable: false,
  })
}

/** 風向量（對應舊 windArrows）：WD 為來向，箭頭轉吹向 WD+180，箭長隨風速。 */
export function windVectorLayer(
  cells: Cell[],
  lead: LeadData,
  leadKey: string,
): Layer {
  const arrows: Arrow[] = []
  for (let i = 0; i < cells.length; i += STRIDE) {
    const s = lead.ws[i]
    const d = lead.wd[i]
    if (s == null || d == null || s < 0.5) continue
    const blowTo = (d + 180) % 360
    arrows.push({
      position: [cells[i].lon, cells[i].lat],
      angle: ccwFromBearing(blowTo),
      size: Math.min(22, Math.round(13 + s)),
    })
  }
  return new IconLayer<Arrow>({
    id: `windVector-${leadKey}`,
    data: arrows,
    getIcon: () => ICON,
    getPosition: (d) => d.position,
    getAngle: (d) => d.angle,
    getSize: (d) => d.size,
    getColor: WIND_COLOR,
    sizeUnits: 'pixels',
    pickable: false,
  })
}
