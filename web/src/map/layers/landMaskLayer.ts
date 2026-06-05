import { GeoJsonLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type { CoastGeoJSON } from '@/data/contracts'

/** 陸地遮罩（對應舊 L.geoJSON land pane）：填 #26344d、線 #6f8db3。 */
export function landMaskLayer(coast: CoastGeoJSON): Layer {
  return new GeoJsonLayer({
    id: 'landMask',
    // deck.gl 的 GeoJSON 型別較嚴格，本地寬鬆型別需轉接。
    data: coast as unknown as string,
    filled: true,
    stroked: true,
    getFillColor: [38, 52, 77, 255], // #26344d
    getLineColor: [111, 141, 179, 255], // #6f8db3
    lineWidthMinPixels: 1,
    pickable: false,
  })
}
