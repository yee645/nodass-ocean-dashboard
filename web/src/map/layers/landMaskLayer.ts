import { GeoJsonLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { CoastGeoJSON } from '@/data/contracts'

export function landMaskLayer(coast: CoastGeoJSON): Layer {
  // 沿用原版 Leaflet land pane：不透明填色蓋在格網上層，遮去溢出到陸地/河口的格子。
  return new GeoJsonLayer({
    id: 'landMask',
    data: coast as unknown as string,
    filled: true,
    getFillColor: [38, 52, 77, 255], // #26344d
    stroked: true,
    getLineColor: [111, 141, 179, 210], // #6f8db3
    lineWidthMinPixels: 1,
    pickable: false,
  })
}
