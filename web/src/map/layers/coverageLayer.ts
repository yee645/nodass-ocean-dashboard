/**
 * 「現在」頁資料涵蓋邊界（issue #15）：現在頁沒有連續格網底色，使用者只看到零星浮標點，
 * 點在涵蓋範圍外才被動跳出「此位置沒有鄰近的浮標內插資料」提示。這裡改成主動用虛線框
 * 標出浮標 IDW 可內插的網格範圍，讓「有資料/無資料」一眼可辨，不需要先點過才知道。
 */
import { PathLayer } from '@deck.gl/layers'
import { PathStyleExtension } from '@deck.gl/extensions'
import type { PathStyleExtensionProps } from '@deck.gl/extensions'
import type { Layer } from '@deck.gl/core'
import type { FishCell } from '@/data/contracts'

type PathDatum = [number, number][]

const gridKey = (lat: number, lon: number, step: number): string =>
  `${Math.round(lat / step)}|${Math.round(lon / step)}`

export function gridCoverageLayer(grid: FishCell[], step: number): Layer {
  const half = step / 2
  const has = new Set(grid.map((c) => gridKey(c.lat, c.lon, step)))
  const paths: PathDatum[] = []
  for (const c of grid) {
    if (!has.has(gridKey(c.lat + step, c.lon, step)))
      paths.push([
        [c.lon - half, c.lat + half],
        [c.lon + half, c.lat + half],
      ])
    if (!has.has(gridKey(c.lat - step, c.lon, step)))
      paths.push([
        [c.lon - half, c.lat - half],
        [c.lon + half, c.lat - half],
      ])
    if (!has.has(gridKey(c.lat, c.lon + step, step)))
      paths.push([
        [c.lon + half, c.lat - half],
        [c.lon + half, c.lat + half],
      ])
    if (!has.has(gridKey(c.lat, c.lon - step, step)))
      paths.push([
        [c.lon - half, c.lat - half],
        [c.lon - half, c.lat + half],
      ])
  }
  return new PathLayer<PathDatum, PathStyleExtensionProps<PathDatum>>({
    id: 'gridField-coverage',
    data: paths,
    getPath: (d) => d,
    getColor: [148, 178, 214, 170],
    getWidth: 1.5,
    widthUnits: 'pixels',
    pickable: false,
    getDashArray: [3, 2],
    dashJustified: true,
    extensions: [new PathStyleExtension({ dash: true })],
  })
}
