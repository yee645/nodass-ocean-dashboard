/**
 * 把「現在」時段的 fishing_grid 併入水深/保育區/陸地限制，組成餵給 costGrid/astar 的 RouteCell[]。
 */
import type { FishCell, Species, CoastGeoJSON } from '@/data/contracts'
import type { DepthBand, RestrictedZone } from '@/data/useExtras'
import type { RouteCell } from './costGrid'
import { isLand, pointInRing } from '../layers/coastMask'
import { suit } from '../layers/nowMath'

export interface BuildRouteCellsInput {
  grid: FishCell[]
  month: number
  species: Species | null
  coast?: CoastGeoJSON
  depthBands?: DepthBand[]
  zones?: RestrictedZone[]
  draftM: number // 吃水限制(公尺)，0 = 不限
  avoidZones: boolean
  tideOffsetM?: number // 最近潮汐測站目前潮位(公尺)，加到水深門檻做單點修正；預設 0(不修正)
}

interface BandBox extends DepthBand {
  bbox: [number, number, number, number] // minLon, minLat, maxLon, maxLat，pointInRing 前的快速排除
}

function withBbox(bands: DepthBand[]): BandBox[] {
  return bands.map((b) => {
    let minLon = Infinity
    let minLat = Infinity
    let maxLon = -Infinity
    let maxLat = -Infinity
    for (const [lon, lat] of b.polygon) {
      if (lon < minLon) minLon = lon
      if (lon > maxLon) maxLon = lon
      if (lat < minLat) minLat = lat
      if (lat > maxLat) maxLat = lat
    }
    return { ...b, bbox: [minLon, minLat, maxLon, maxLat] }
  })
}

/** 涵蓋該點的等深帶中最淺(保守)的下限水深；找不到涵蓋的帶時回傳 null(無資料，不擋)。 */
function shallowestMinDepth(bands: BandBox[], lon: number, lat: number): number | null {
  let best: number | null = null
  for (const b of bands) {
    const [minLon, minLat, maxLon, maxLat] = b.bbox
    if (lon < minLon || lon > maxLon || lat < minLat || lat > maxLat) continue
    if (!pointInRing(lon, lat, b.polygon)) continue
    if (best === null || b.minDepth < best) best = b.minDepth
  }
  return best
}

export function buildRouteCells(input: BuildRouteCellsInput): RouteCell[] {
  const { grid, month, species, coast, depthBands, zones, draftM, avoidZones, tideOffsetM = 0 } = input
  const bands = depthBands ? withBbox(depthBands) : null

  return grid.map((cell) => {
    let blocked = isLand(cell.lon, cell.lat, coast)

    if (!blocked && bands && draftM > 0) {
      const depth = shallowestMinDepth(bands, cell.lon, cell.lat)
      if (depth != null && depth + tideOffsetM < draftM) blocked = true
    }

    if (!blocked && avoidZones && zones) {
      for (const zone of zones) {
        if (pointInRing(cell.lon, cell.lat, zone.polygon)) {
          blocked = true
          break
        }
      }
    }

    const score = species
      ? suit(cell.v, species, month, { u: cell.u, w: cell.w, trend: cell.tr }) / 100
      : 0

    return {
      lat: cell.lat,
      lon: cell.lon,
      score,
      wave: cell.wave ?? null,
      u: cell.u,
      w: cell.w,
      land: blocked,
    }
  })
}
