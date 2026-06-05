import type { CoastGeoJSON, FishCell } from '@/data/contracts'

type Ring = number[][]

function pointInRing(lon: number, lat: number, ring: Ring): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0]
    const yi = ring[i][1]
    const xj = ring[j][0]
    const yj = ring[j][1]
    const hit =
      yi > lat !== yj > lat &&
      lon < ((xj - xi) * (lat - yi)) / (yj - yi || Number.EPSILON) + xi
    if (hit) inside = !inside
  }
  return inside
}

function inPolygon(lon: number, lat: number, polygon: number[][][]): boolean {
  if (!polygon.length || !pointInRing(lon, lat, polygon[0])) return false
  for (let i = 1; i < polygon.length; i++) {
    if (pointInRing(lon, lat, polygon[i])) return false
  }
  return true
}

export function isLand(
  lon: number,
  lat: number,
  coast?: CoastGeoJSON,
): boolean {
  if (!coast) return false
  for (const feature of coast.features) {
    const { geometry } = feature
    if (geometry.type === 'Polygon') {
      if (inPolygon(lon, lat, geometry.coordinates as number[][][])) return true
    } else {
      for (const polygon of geometry.coordinates as number[][][][]) {
        if (inPolygon(lon, lat, polygon)) return true
      }
    }
  }
  return false
}

export function cellTouchesLand(
  cell: FishCell,
  step: number,
  coast?: CoastGeoJSON,
): boolean {
  const half = step / 2
  const samples: [number, number][] = [
    [cell.lon, cell.lat],
    [cell.lon - half, cell.lat - half],
    [cell.lon + half, cell.lat - half],
    [cell.lon + half, cell.lat + half],
    [cell.lon - half, cell.lat + half],
    [cell.lon, cell.lat - half],
    [cell.lon, cell.lat + half],
    [cell.lon - half, cell.lat],
    [cell.lon + half, cell.lat],
  ]
  return samples.some(([lon, lat]) => isLand(lon, lat, coast))
}

export function segmentTouchesLand(
  from: [number, number],
  to: [number, number],
  coast?: CoastGeoJSON,
): boolean {
  if (!coast) return false
  const samples = 10
  for (let i = 0; i <= samples; i++) {
    const t = i / samples
    const lon = from[0] + (to[0] - from[0]) * t
    const lat = from[1] + (to[1] - from[1]) * t
    if (isLand(lon, lat, coast)) return true
  }
  return false
}

export function nearestSeaPosition(
  lon: number,
  lat: number,
  coast?: CoastGeoJSON,
): [number, number] | null {
  if (!coast || !isLand(lon, lat, coast)) return [lon, lat]

  const radii = [0.03, 0.05, 0.08, 0.12, 0.18, 0.26, 0.36, 0.5]
  for (const radius of radii) {
    for (let i = 0; i < 24; i++) {
      const angle = (i / 24) * Math.PI * 2
      const candidateLon = lon + Math.cos(angle) * radius
      const candidateLat = lat + Math.sin(angle) * radius
      if (!isLand(candidateLon, candidateLat, coast)) {
        return [candidateLon, candidateLat]
      }
    }
  }

  return null
}
