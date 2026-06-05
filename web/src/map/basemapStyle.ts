import type { StyleSpecification } from 'maplibre-gl'

// 暗色底圖：沿用舊版 CartoDB dark_all 圖磚（MapLibre raster 以多個完整 URL 取代 {s} 子網域）。
const CARTO = ['a', 'b', 'c', 'd'].map(
  (s) => `https://${s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png`,
)

export const basemapStyle: StyleSpecification = {
  version: 8,
  sources: {
    carto: {
      type: 'raster',
      tiles: CARTO,
      tileSize: 256,
      attribution: '&copy; OpenStreetMap &copy; CARTO',
    },
  },
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': '#0a1a2e' } },
    { id: 'carto', type: 'raster', source: 'carto' },
  ],
}
