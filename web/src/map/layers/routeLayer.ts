import { PathLayer, ScatterplotLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { RouteResult, RoutePoint } from '../route/astar'
import { haversineKm } from '../route/astar'

const ROUTE_COLOR: [number, number, number] = [255, 208, 0] // #ffd000
const START_COLOR: [number, number, number] = [46, 147, 108] // 綠：起點
const END_COLOR: [number, number, number] = [215, 38, 61] // 紅：終點
const WAYPOINT_COLOR: [number, number, number] = [127, 212, 255] // 藍白：中繼點
const KM_PER_NM = 1.852

interface RouteSegment {
  path: [number, number][]
  cumKm: number // 從起點累積到本段終點的距離
}

/** 把 A* 結果切成逐段資料，附帶累積距離，供 hover tooltip 顯示「這裡距起點多遠/預估幾小時」。 */
function buildSegments(path: [number, number][]): RouteSegment[] {
  const segments: RouteSegment[] = []
  let cum = 0
  for (let i = 1; i < path.length; i++) {
    const [lonA, latA] = path[i - 1]
    const [lonB, latB] = path[i]
    cum += haversineKm(latA, lonA, latB, lonB)
    segments.push({ path: [path[i - 1], path[i]], cumKm: cum })
  }
  return segments
}

/** PathLayer 的 hover info.object 是否為航線段落（供 MapView 的 getTooltip 判斷）。 */
export function isRouteSegment(obj: unknown): obj is RouteSegment {
  return !!obj && typeof (obj as RouteSegment).cumKm === 'number' && Array.isArray((obj as RouteSegment).path)
}

export function routeSegmentTooltip(seg: RouteSegment, speedKt: number): string {
  const nm = seg.cumKm / KM_PER_NM
  const hours = nm / speedKt
  return `距起點 ${nm.toFixed(1)} 浬・預估 ${hours.toFixed(1)} 小時`
}

/** 航線本體（第二層規劃結果，可含中繼點）+ 起訖點/中繼點標記。 */
export function routeLayers(
  result: RouteResult | null,
  start: RoutePoint | null,
  end: RoutePoint | null,
  waypoints: RoutePoint[],
): Layer[] {
  const layers: Layer[] = []

  if (result) {
    layers.push(
      new PathLayer<RouteSegment>({
        id: 'route-path',
        data: buildSegments(result.path),
        getPath: (d) => d.path,
        getColor: ROUTE_COLOR,
        getWidth: 4,
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
        pickable: true,
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

  if (waypoints.length) {
    layers.push(
      new ScatterplotLayer<RoutePoint>({
        id: 'route-waypoint',
        data: waypoints,
        getPosition: (d) => [d.lon, d.lat],
        getFillColor: WAYPOINT_COLOR,
        getLineColor: [255, 255, 255],
        lineWidthUnits: 'pixels',
        getLineWidth: 1.5,
        stroked: true,
        radiusUnits: 'pixels',
        getRadius: 5,
        pickable: false,
      }),
    )
  }

  return layers
}
