/**
 * 第一層 · 魚場核心熱區的 deck.gl 圖層（接線層）。
 *
 * 串接：同學 nowMath.suit()(環境適合度) × 我的 hotspotModel(出現密度 + 信心 + 取核心)，
 * 產出「小而集中、貼近真實漁場」的核心熱區，取代固定 HOT_THR=70 的大塊熱區。
 * 樣式沿用同學 nowLayers 的金色填色 + 外框 + 海流漂移箭頭，視覺一致。
 */
import {
  PolygonLayer,
  PathLayer,
  LineLayer,
  IconLayer,
  TextLayer,
} from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { FishCell, Species } from '@/data/contracts'
import type { OccRaw } from '@/data/useExtras'
import { suit } from './nowMath'
import {
  occurrenceDensity,
  occurrenceCount,
  confidenceFromOccurrence,
  fishScore,
  extractCores,
  type OccPoint,
} from './hotspotModel'

const MIN_PRESENCE = 2 // 核心至少需這麼多出現點(半徑內)支持，濾掉單點雜訊假核(如秋刀魚/旗魚)

const ccwFromBearing = (bearing: number): number => (360 - bearing) % 360

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

const gridKey = (lat: number, lon: number, step: number): string =>
  `${Math.round(lat / step)}|${Math.round(lon / step)}`

/**
 * 產生現在時段「核心熱區」圖層群。
 * @param grid  現在頁網格(含 v=SST, u/w=海流, tr=趨勢)
 * @param sp    魚種(含同學的權重/鐘形參數)
 * @param month 月份
 * @param step  網格度數
 * @param occRaw 該頁出現點(精簡格式)
 */
export function hotspotCoreLayers(
  grid: FishCell[],
  sp: Species,
  month: number,
  step: number,
  occRaw: OccRaw[],
): Layer[] {
  const occ: OccPoint[] = occRaw.map((o) => ({
    species: o.s,
    lat: o.lat,
    lon: o.lon,
    month: o.m,
  }))

  // 1. 環境適合度：吃同學的 suit（front 在網格暫無 → 0，與現況一致；其餘 SST/海流/季節/趨勢照算）
  const envSuit = grid.map((c) =>
    suit(c.v, sp, month, { u: c.u ?? null, w: c.w ?? null, trend: c.tr ?? null }),
  )
  // 2. 歷史出現密度 → 相乘 gate；3. 信心 → 取核心門檻
  const density = occurrenceDensity(grid, occ, sp.name, month)
  const score = fishScore(envSuit, density)
  const conf = confidenceFromOccurrence(grid, occ, sp.name, month)
  // 最小出現支持：核心需有 ≥MIN_PRESENCE 個出現點落在其格附近，否則視為單點雜訊濾掉
  const presence = occurrenceCount(grid, occ, sp.name)
  const cores = extractCores(score, conf, grid, step).filter((core) =>
    core.cellIdx.some((i) => presence[i] >= MIN_PRESENCE),
  )
  if (!cores.length) return []

  const half = step / 2
  const fillCells: FishCell[] = []
  const outline: { path: [number, number][] }[] = []
  const driftLines: { from: [number, number]; to: [number, number] }[] = []
  const arrows: { position: [number, number]; angle: number }[] = []
  const labels: { position: [number, number]; text: string }[] = []

  for (const core of cores) {
    const keys = new Set(
      core.cellIdx.map((i) => gridKey(grid[i].lat, grid[i].lon, step)),
    )
    for (const i of core.cellIdx) {
      const c = grid[i]
      fillCells.push(c)
      if (!keys.has(gridKey(c.lat + step, c.lon, step)))
        outline.push({ path: [[c.lon - half, c.lat + half], [c.lon + half, c.lat + half]] })
      if (!keys.has(gridKey(c.lat - step, c.lon, step)))
        outline.push({ path: [[c.lon - half, c.lat - half], [c.lon + half, c.lat - half]] })
      if (!keys.has(gridKey(c.lat, c.lon + step, step)))
        outline.push({ path: [[c.lon + half, c.lat - half], [c.lon + half, c.lat + half]] })
      if (!keys.has(gridKey(c.lat, c.lon - step, step)))
        outline.push({ path: [[c.lon - half, c.lat - half], [c.lon - half, c.lat + half]] })
    }
    const [cLon, cLat] = core.centroid
    labels.push({
      position: [cLon, cLat],
      text: `魚群熱區${core.drift ? `·往${core.drift.dir}` : ''}`,
    })
    // 海流方向(可能漂移)：短而有界的方向箭頭，貼著核心(不再用流速×大係數的長向量，
    // 以免在縮小後的核心上射出老遠、看似與熱區無關)；流速太小(近乎無流)就不畫，避免亂指。
    if (core.drift && core.drift.spd > 0.02) {
      const rad = (core.drift.deg * Math.PI) / 180
      const len = Math.min(0.11, 0.05 + core.drift.spd * 0.12) // 度：短、輕微隨流速、上限約 12km
      const lat2 = cLat + Math.cos(rad) * len
      const lon2 = cLon + Math.sin(rad) * len
      driftLines.push({ from: [cLon, cLat], to: [lon2, lat2] })
      arrows.push({ position: [lon2, lat2], angle: ccwFromBearing(core.drift.deg) })
    }
  }

  return [
    new PolygonLayer<FishCell>({
      id: 'hotspot-fill',
      data: fillCells,
      getPolygon: (c) => [
        [c.lon - half, c.lat - half],
        [c.lon + half, c.lat - half],
        [c.lon + half, c.lat + half],
        [c.lon - half, c.lat + half],
      ],
      getFillColor: [255, 208, 0, 80],
      stroked: false,
      filled: true,
      pickable: false,
      updateTriggers: { getPolygon: [sp.name, month] },
    }),
    new PathLayer<{ path: [number, number][] }>({
      id: 'hotspot-outline',
      data: outline,
      getPath: (d) => d.path,
      getColor: [255, 208, 0, 235],
      getWidth: 2,
      widthUnits: 'pixels',
      pickable: false,
      updateTriggers: { getPath: [sp.name, month] },
    }),
    new LineLayer<{ from: [number, number]; to: [number, number] }>({
      id: 'hotspot-drift-line',
      data: driftLines,
      getSourcePosition: (d) => d.from,
      getTargetPosition: (d) => d.to,
      getColor: [127, 212, 255, 242],
      getWidth: 2.5,
      widthUnits: 'pixels',
      pickable: false,
    }),
    new IconLayer<{ position: [number, number]; angle: number }>({
      id: 'hotspot-drift-arrow',
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
      id: 'hotspot-label',
      data: labels,
      getPosition: (d) => d.position,
      getText: (d) => d.text,
      getColor: [255, 208, 0],
      getSize: 11,
      sizeUnits: 'pixels',
      getPixelOffset: [0, -14],
      fontFamily: "'Microsoft JhengHei', 'Segoe UI', sans-serif",
      characterSet: 'auto',
      outlineColor: [0, 0, 0, 255],
      outlineWidth: 2,
      fontSettings: { sdf: true },
      pickable: false,
    }),
  ]
}
