/**
 * 把「現在」時段的 fishing_grid 併入水深/保育區/陸地限制，組成餵給 costGrid/astar 的 RouteCell[]。
 */
import type { FishCell, Species, CoastGeoJSON } from '@/data/contracts'
import type { BathymetryPayload, RestrictedZone } from '@/data/useExtras'
import type { RouteCell } from './costGrid'
import { isLand, pointInRing } from '../layers/coastMask'
import { suit } from '../layers/nowMath'

export interface BuildRouteCellsInput {
  grid: FishCell[]
  month: number
  species: Species | null
  coast?: CoastGeoJSON
  bathymetry?: BathymetryPayload
  zones?: RestrictedZone[]
  draftM: number // 吃水限制(公尺)，0 = 不限
  avoidZones: boolean
  tideOffsetM?: number // 最近潮汐測站目前潮位(公尺)，加到水深門檻做單點修正；預設 0(不修正)
}

export function buildRouteCells(input: BuildRouteCellsInput): RouteCell[] {
  const { grid, month, species, coast, bathymetry, zones, draftM, avoidZones, tideOffsetM = 0 } = input

  const depthByKey = new Map<string, number>()
  if (bathymetry) {
    for (const c of bathymetry.cells) {
      const key = `${Math.round(c.lat / bathymetry.step)}|${Math.round(c.lon / bathymetry.step)}`
      depthByKey.set(key, c.depth)
    }
  }

  return grid.map((cell) => {
    let blocked = isLand(cell.lon, cell.lat, coast)

    if (!blocked && bathymetry && draftM > 0) {
      const key = `${Math.round(cell.lat / bathymetry.step)}|${Math.round(cell.lon / bathymetry.step)}`
      const depth = depthByKey.get(key)
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
