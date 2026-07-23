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
import { gridFieldLayer } from './layers/gridFieldLayer'
import { currentVectorLayer, windVectorLayer } from './layers/vectorLayers'
import {
  hotZoneLayers,
  stationLayer,
} from './layers/nowLayers'
import { hotspotCoreLayers } from './layers/hotspotLayers'
import { gridCoverageLayer } from './layers/coverageLayer'
import { useOccurrences, useBathymetry, useSdmNow } from '@/data/useExtras'
import { hiresGridLayer } from './layers/hiresLayer'
import { resolveHiresKeys } from './layers/hiresMath'
import { landMaskLayer } from './layers/landMaskLayer'
import { bathymetryLayer } from './layers/bathymetryLayer'
import { routeLayers } from './layers/routeLayer'
import { orderLayers } from './layerOrder'

export function useDeckLayers(): Layer[] {
  const timeMode = useAppStore((s) => s.timeMode)
  const baseField = useAppStore((s) => s.baseField)
  const species = useAppStore((s) => s.species)
  const confDim = useAppStore((s) => s.confDim)
  const leadIndex = useAppStore((s) => s.leadIndex)
  const overlays = useAppStore((s) => s.overlays)
  const fishMove = useAppStore((s) => s.fishMove)
  const routeResult = useAppStore((s) => s.routeResult)
  const routeStart = useAppStore((s) => s.routeStart)
  const routeEnd = useAppStore((s) => s.routeEnd)
  const routeWaypoints = useAppStore((s) => s.routeWaypoints)
  const routeShowDepth = useAppStore((s) => s.routeShowDepth)

  const { data: coast } = useCoast()
  const { data: forecast } = useForecastData()
  const { data: fishing } = useFishingData()
  const { data: hires } = useHiresData()
  const { data: occ } = useOccurrences()
  const { data: bathymetry } = useBathymetry()
  const { data: sdmNow } = useSdmNow()
  const { grid: nowGrid } = useNowGrid()

  return useMemo<Layer[]>(() => {
    const layers: (Layer | null)[] = []

    // 格網模式(future/past)以不透明陸地遮罩蓋住溢出陸地的格子；now 模式漂移層自行擦除陸地。
    if (coast && (timeMode === 'future' || timeMode === 'past')) {
      layers.push(landMaskLayer(coast))
    }

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
        if (overlays.current) layers.push(currentVectorLayer(cells, lead, leadKey))
        if (overlays.wind) layers.push(windVectorLayer(cells, lead, leadKey))
      }
    }

    if (timeMode === 'now' && fishing) {
      const { meta, species: speciesOptions, stations } = fishing
      const grid = nowGrid ?? fishing.grid
      layers.push(gridCoverageLayer(grid, meta.step))
      const currentSpecies = species.length ? species[0] : null
      const sp = currentSpecies
        ? (speciesOptions.find((s) => s.name === currentSpecies) ?? null)
        : null
      if (sp) {
        if (fishMove) {
          // 出現點到位 → 用「核心熱區」(環境×歷史出現密度×信心，取核心，貼近真實)；
          // 尚未載入時回退同學原本的整片熱區，避免空窗。
          if (occ && occ.length) {
            layers.push(...hotspotCoreLayers(grid, sp, meta.month, meta.step, occ, sdmNow))
          } else {
            layers.push(...hotZoneLayers(grid, sp, meta.month, meta.step))
          }
        }
      }
      layers.push(stationLayer(stations, sp ? sp.name : null))
      if (routeShowDepth && bathymetry) layers.push(bathymetryLayer(bathymetry))
      layers.push(...routeLayers(routeResult, routeStart, routeEnd, routeWaypoints))
    }

    if (timeMode === 'past' && hires) {
      const { meta, lat, lon, layers: layerData } = hires
      const speciesKeys = resolveHiresKeys(layerData, species)
      const layer = hiresGridLayer({
        lat,
        lon,
        layers: layerData,
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
    occ,
    nowGrid,
    timeMode,
    baseField,
    species,
    confDim,
    leadIndex,
    overlays,
    fishMove,
    routeResult,
    routeStart,
    routeEnd,
    routeWaypoints,
    routeShowDepth,
    bathymetry,
    sdmNow,
  ])
}
