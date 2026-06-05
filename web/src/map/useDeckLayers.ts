import { useMemo } from 'react'
import type { Layer } from '@deck.gl/core'
import { useAppStore } from '@/store/useAppStore'
import {
  useCoast,
  useFishingData,
  useForecastData,
  useHiresData,
} from '@/data/useData'
import { useNowGrid } from './useNowGrid'
import { landMaskLayer } from './layers/landMaskLayer'
import { gridFieldLayer } from './layers/gridFieldLayer'
import { currentVectorLayer, windVectorLayer } from './layers/vectorLayers'
import {
  suitabilityGridLayer,
  hotZoneLayers,
  stationLayer,
} from './layers/nowLayers'
import { hiresGridLayer } from './layers/hiresLayer'
import { resolveHiresKeys } from './layers/hiresMath'
import { orderLayers } from './layerOrder'

/**
 * 依 store + 資料組裝 deck.gl 圖層，並以 orderLayers 固定堆疊順序。
 * 目前打通「未來時段」端到端：landMask + gridField(互斥純量場)。
 * 海流/風向量、出現點、浮標、過去/現在時段於後續步驟接入。
 */
export function useDeckLayers(): Layer[] {
  const timeMode = useAppStore((s) => s.timeMode)
  const baseField = useAppStore((s) => s.baseField)
  const species = useAppStore((s) => s.species)
  const confDim = useAppStore((s) => s.confDim)
  const leadIndex = useAppStore((s) => s.leadIndex)
  const overlays = useAppStore((s) => s.overlays)
  const fishMove = useAppStore((s) => s.fishMove)

  const { data: coast } = useCoast()
  const { data: forecast } = useForecastData()
  const { data: fishing } = useFishingData()
  const { data: hires } = useHiresData()
  const { grid: nowGrid } = useNowGrid() // 依時間軸重算後的現在時段網格

  return useMemo<Layer[]>(() => {
    const layers: (Layer | null)[] = []
    if (coast) layers.push(landMaskLayer(coast))

    if (timeMode === 'future' && forecast) {
      const { meta, cells, chl, conf, data } = forecast
      const li = Math.max(0, Math.min(meta.leads.length - 1, leadIndex))
      const leadKey = String(meta.leads[li].d)
      const lead = data[leadKey]
      if (lead) {
        layers.push(
          gridFieldLayer({
            cells,
            step: meta.step,
            baseField,
            lead,
            leadKey,
            chl,
            conf,
            species,
            confDim,
          }),
        )
        if (overlays.current)
          layers.push(currentVectorLayer(cells, lead, leadKey))
        if (overlays.wind) layers.push(windVectorLayer(cells, lead, leadKey))
      }
    }

    if (timeMode === 'now' && fishing) {
      const { meta, species: SP, stations } = fishing
      const grid = nowGrid ?? fishing.grid
      const cur = species.length ? species[0] : null // 空=綜合潛在漁場(OVERALL)
      const sp = cur ? (SP.find((s) => s.name === cur) ?? null) : null
      if (sp) {
        layers.push(suitabilityGridLayer(grid, sp, meta.month, meta.step))
        if (fishMove)
          layers.push(...hotZoneLayers(grid, sp, meta.month, meta.step))
      }
      layers.push(stationLayer(stations, sp ? sp.name : null))
    }

    if (timeMode === 'past' && hires) {
      const { meta, lat, lon, layers: L } = hires
      const speciesKeys = resolveHiresKeys(L, species)
      const layer = hiresGridLayer({
        lat,
        lon,
        layers: L,
        step: meta.step,
        baseField,
        speciesKeys,
        confDim,
      })
      if (layer) layers.push(layer)
    }

    return orderLayers(layers)
  }, [
    coast,
    forecast,
    fishing,
    hires,
    nowGrid,
    timeMode,
    baseField,
    species,
    confDim,
    leadIndex,
    overlays,
    fishMove,
  ])
}
