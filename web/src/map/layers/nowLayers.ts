import {
  PolygonLayer,
  ScatterplotLayer,
  PathLayer,
  LineLayer,
  IconLayer,
  TextLayer,
} from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { FishCell, Species, Station } from '@/data/contracts'
import { suit, heat, colorFor, bearingDeg, dirName, scoreBand } from './nowMath'

const HOT_THR = 70
const ccwFromBearing = (bearing: number): number => (360 - bearing) % 360
const hotAlpha = (value: number): number =>
  Math.round(54 + ((Math.max(HOT_THR, scoreBand(value)) - HOT_THR) / (90 - HOT_THR)) * 42)

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

export function suitabilityGridLayer(
  grid: FishCell[],
  sp: Species,
  month: number,
  step: number,
): Layer {
  const half = step / 2
  const cells = grid
    .map((cell) => ({
      cell,
      value: suit(cell.v, sp, month, { u: cell.u, w: cell.w, trend: cell.tr }),
    }))
    .filter((item) => item.value > 0)

  return new PolygonLayer<{ cell: FishCell; value: number }>({
    id: 'gridField-suit',
    data: cells,
    getPolygon: ({ cell }) => [
      [cell.lon - half, cell.lat - half],
      [cell.lon + half, cell.lat - half],
      [cell.lon + half, cell.lat + half],
      [cell.lon - half, cell.lat + half],
    ],
    getFillColor: ({ value }) => {
      const [r, g, b] = heat(value)
      return [r, g, b, 128]
    },
    stroked: false,
    filled: true,
    pickable: false,
    updateTriggers: { getFillColor: [sp.name, month] },
  })
}

export function stationLayer(
  stations: Station[],
  mode: string | null,
): Layer {
  const valOf = (station: Station): number =>
    mode == null ? station.fish_score : (station.species[mode] ?? 0)

  return new ScatterplotLayer<Station>({
    id: 'buoy-stations',
    data: stations,
    getPosition: (station) => [station.lon, station.lat],
    getRadius: (station) => 5 + valOf(station) / 12,
    radiusUnits: 'pixels',
    getFillColor: (station) => {
      const [r, g, b] = colorFor(valOf(station))
      return [r, g, b, 242]
    },
    getLineColor: [255, 255, 255],
    lineWidthMinPixels: 1.2,
    stroked: true,
    filled: true,
    pickable: true,
    updateTriggers: { getRadius: [mode], getFillColor: [mode] },
  })
}

interface HotCell {
  cell: FishCell
  value: number
}

const gridKey = (lat: number, lon: number, step: number): string =>
  `${Math.round(lat / step)}|${Math.round(lon / step)}`

function clusters(
  grid: FishCell[],
  sp: Species,
  month: number,
  step: number,
): HotCell[][] {
  const hot: HotCell[] = grid
    .map((cell) => ({
      cell,
      value: suit(cell.v, sp, month, { u: cell.u, w: cell.w, trend: cell.tr }),
    }))
    .filter((item) => item.value >= HOT_THR)
  const byKey = new Map<string, HotCell>()
  hot.forEach((item) => byKey.set(gridKey(item.cell.lat, item.cell.lon, step), item))

  const seen = new Set<string>()
  const groups: HotCell[][] = []
  const neighbors = [
    [step, 0],
    [-step, 0],
    [0, step],
    [0, -step],
  ]

  for (const item of hot) {
    const startKey = gridKey(item.cell.lat, item.cell.lon, step)
    if (seen.has(startKey)) continue
    const stack = [item]
    const group: HotCell[] = []
    seen.add(startKey)

    while (stack.length) {
      const current = stack.pop()!
      group.push(current)
      for (const [dLat, dLon] of neighbors) {
        const key = gridKey(current.cell.lat + dLat, current.cell.lon + dLon, step)
        const next = byKey.get(key)
        if (next && !seen.has(key)) {
          seen.add(key)
          stack.push(next)
        }
      }
    }
    groups.push(group)
  }

  return groups
}

export function hotZoneLayers(
  grid: FishCell[],
  sp: Species,
  month: number,
  step: number,
): Layer[] {
  const groups = clusters(grid, sp, month, step)
  if (!groups.length) return []
  const half = step / 2

  const fillCells: HotCell[] = []
  const outline: { path: [number, number][]; value: number }[] = []
  const driftLines: { from: [number, number]; to: [number, number] }[] = []
  const arrows: { position: [number, number]; angle: number }[] = []
  const labels: { position: [number, number]; text: string }[] = []

  for (const group of groups) {
    const keys = new Set(group.map((item) => gridKey(item.cell.lat, item.cell.lon, step)))
    for (const item of group) {
      const { cell, value } = item
      fillCells.push(item)
      if (!keys.has(gridKey(cell.lat + step, cell.lon, step))) {
        outline.push({
          value,
          path: [
            [cell.lon - half, cell.lat + half],
            [cell.lon + half, cell.lat + half],
          ],
        })
      }
      if (!keys.has(gridKey(cell.lat - step, cell.lon, step))) {
        outline.push({
          value,
          path: [
            [cell.lon - half, cell.lat - half],
            [cell.lon + half, cell.lat - half],
          ],
        })
      }
      if (!keys.has(gridKey(cell.lat, cell.lon + step, step))) {
        outline.push({
          value,
          path: [
            [cell.lon + half, cell.lat - half],
            [cell.lon + half, cell.lat + half],
          ],
        })
      }
      if (!keys.has(gridKey(cell.lat, cell.lon - step, step))) {
        outline.push({
          value,
          path: [
            [cell.lon - half, cell.lat - half],
            [cell.lon - half, cell.lat + half],
          ],
        })
      }
    }

    const currentCells = group.filter((item) => item.cell.u !== undefined)
    let avgU = 0
    let avgW = 0
    currentCells.forEach((item) => {
      avgU += item.cell.u!
      avgW += item.cell.w!
    })

    const hasCurrent = currentCells.length > 0
    if (hasCurrent) {
      avgU /= currentCells.length
      avgW /= currentCells.length
    }

    const speed = hasCurrent ? Math.hypot(avgU, avgW) : null
    const bearing = speed != null ? bearingDeg(avgU, avgW) : null
    const direction = bearing != null ? dirName(bearing) : null
    const centerLat =
      group.reduce((sum, item) => sum + item.cell.lat, 0) / group.length
    const centerLon =
      group.reduce((sum, item) => sum + item.cell.lon, 0) / group.length

    labels.push({
      position: [centerLon, centerLat],
      text: `魚群熱區${direction ? `·往${direction}` : ''}`,
    })

    if (speed != null && speed > 0.001 && bearing != null) {
      const scale = 0.9
      const lat2 = centerLat + avgW * scale
      const lon2 = centerLon + avgU * scale
      driftLines.push({ from: [centerLon, centerLat], to: [lon2, lat2] })
      arrows.push({ position: [lon2, lat2], angle: ccwFromBearing(bearing) })
    }
  }

  return [
    new PolygonLayer<HotCell>({
      id: 'drift-fill',
      data: fillCells,
      getPolygon: ({ cell }) => [
        [cell.lon - half, cell.lat - half],
        [cell.lon + half, cell.lat - half],
        [cell.lon + half, cell.lat + half],
        [cell.lon - half, cell.lat + half],
      ],
      getFillColor: ({ value }) => {
        const [r, g, b] = heat(value)
        return [r, g, b, hotAlpha(value)]
      },
      stroked: false,
      filled: true,
      pickable: false,
      updateTriggers: {
        getPolygon: [sp.name, month],
        getFillColor: [sp.name, month],
      },
    }),
    new PathLayer<{ path: [number, number][]; value: number }>({
      id: 'drift-outline',
      data: outline,
      getPath: (item) => item.path,
      getColor: ({ value }) => {
        const [r, g, b] = heat(value)
        return [r, g, b, 230]
      },
      getWidth: 2,
      widthUnits: 'pixels',
      pickable: false,
      updateTriggers: {
        getPath: [sp.name, month],
        getColor: [sp.name, month],
      },
    }),
    new LineLayer<{ from: [number, number]; to: [number, number] }>({
      id: 'drift-line',
      data: driftLines,
      getSourcePosition: (item) => item.from,
      getTargetPosition: (item) => item.to,
      getColor: [127, 212, 255, 242],
      getWidth: 2.5,
      widthUnits: 'pixels',
      pickable: false,
    }),
    new IconLayer<{ position: [number, number]; angle: number }>({
      id: 'drift-arrow',
      data: arrows,
      getIcon: () => DRIFT_ICON,
      getPosition: (item) => item.position,
      getAngle: (item) => item.angle,
      getSize: 16,
      getColor: [127, 212, 255],
      sizeUnits: 'pixels',
      pickable: false,
    }),
    new TextLayer<{ position: [number, number]; text: string }>({
      id: 'drift-label',
      data: labels,
      getPosition: (item) => item.position,
      getText: (item) => item.text,
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
