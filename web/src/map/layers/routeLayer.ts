import { PathLayer, ScatterplotLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { RouteResult, RoutePoint } from '../route/astar'

const ROUTE_COLOR: [number, number, number] = [255, 208, 0] // #ffd000
const START_COLOR: [number, number, number] = [46, 147, 108] // 綠：起點
const END_COLOR: [number, number, number] = [215, 38, 61] // 紅：終點

/** 航線本體（第二層規劃結果）+ 起訖點標記。 */
export function routeLayers(
  result: RouteResult | null,
  start: RoutePoint | null,
  end: RoutePoint | null,
): Layer[] {
  const layers: Layer[] = []

  if (result) {
    layers.push(
      new PathLayer<{ path: [number, number][] }>({
        id: 'route-path',
        data: [{ path: result.path }],
        getPath: (d) => d.path,
        getColor: ROUTE_COLOR,
        getWidth: 4,
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
        pickable: false,
      }),
    )
  }

  const marker = (id: string, p: RoutePoint | null, color: [number, number, number]): void => {
    if (!p) return
    layers.push(
      new ScatterplotLayer<RoutePoint>({
        id,
        data: [p],
        getPosition: (d) => [d.lon, d.lat],
        getFillColor: color,
        getLineColor: [255, 255, 255],
        lineWidthUnits: 'pixels',
        getLineWidth: 2,
        stroked: true,
        radiusUnits: 'pixels',
        getRadius: 7,
        pickable: false,
      }),
    )
  }
  marker('route-start', start, START_COLOR)
  marker('route-end', end, END_COLOR)

  return layers
}
