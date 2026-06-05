import { useCallback } from 'react'
import { useAppStore } from '@/store/useAppStore'
import {
  useFishingData,
  useForecastData,
  useHiresData,
} from '@/data/useData'
import { useNowGrid } from './useNowGrid'
import { beaufort } from './palettes'
import { LOWCONF } from './layers/fieldConfig'
import { suit, dirName, bearingDeg } from './layers/nowMath'
import { resolveHiresKeys } from './layers/hiresMath'

const empty = (value: number | null | undefined, suffix = ''): string =>
  value == null ? '-' : `${value}${suffix}`

const confLabel = (value: number): string =>
  value < LOWCONF ? '低' : value < 0.6 ? '中' : '高'

export function usePopup(): (lng: number, lat: number) => string | null {
  const timeMode = useAppStore((s) => s.timeMode)
  const baseField = useAppStore((s) => s.baseField)
  const leadIndex = useAppStore((s) => s.leadIndex)
  const species = useAppStore((s) => s.species)
  const { data: forecast } = useForecastData()
  const { data: fishing } = useFishingData()
  const { data: hires } = useHiresData()
  const { grid: nowGrid } = useNowGrid()

  return useCallback(
    (lng, lat) => {
      if (timeMode === 'future' && forecast) {
        const { meta, cells, chl, conf, data } = forecast
        const lead = meta.leads[Math.max(0, Math.min(meta.leads.length - 1, leadIndex))]
        const leadData = data[String(lead.d)]
        if (!leadData) return null

        let bestIndex = -1
        let bestDistance = Infinity
        for (let i = 0; i < cells.length; i++) {
          const distance = Math.abs(cells[i].lat - lat) + Math.abs(cells[i].lon - lng)
          if (distance < bestDistance) {
            bestDistance = distance
            bestIndex = i
          }
        }

        let html = `位置 ${lat.toFixed(3)}, ${lng.toFixed(3)}`
        if (bestIndex >= 0 && bestDistance <= meta.step * 2 && leadData.sst[bestIndex] != null) {
          const ws = leadData.ws[bestIndex]
          const wd = leadData.wd[bestIndex]
          const wl = leadData.wl[bestIndex]
          const c = conf[bestIndex]
          html += `<br/>SST ${empty(leadData.sst[bestIndex], '°C')} / 海流 ${empty(leadData.cspd[bestIndex], ' m/s')}`
          if (chl[bestIndex] != null) html += `<br/>葉綠素 ${chl[bestIndex]}`
          if (ws != null) {
            html += `<br/>風速 ${ws} m/s（蒲福 ${beaufort(ws)}）`
            if (wd != null) html += ` / 風向 ${wd}°`
            if (wl != null) html += ` / 水位 ${wl} m`
          }
          if (c != null) html += `<br/>資料信心 ${c}（${confLabel(c)}）`

          const names =
            baseField === 'habitat' && species.length ? species : meta.species
          const lines = names
            .map((name) => {
              const value = leadData.s[name]?.[bestIndex]
              return value == null ? null : `${name} ${value}`
            })
            .filter(Boolean)
          if (lines.length) html += '<br/>棲地適合度：' + lines.join(' / ')
        } else {
          html += '<br/>此位置沒有足夠的預報格點資料'
        }
        return html
      }

      if (timeMode === 'now' && fishing) {
        const { meta, species: speciesOptions } = fishing
        const grid = nowGrid ?? fishing.grid
        const cur = species.length ? species[0] : null
        const sp = cur ? (speciesOptions.find((item) => item.name === cur) ?? null) : null
        let best: (typeof grid)[number] | null = null
        let bestDistance = Infinity
        for (const cell of grid) {
          const distance = Math.hypot(cell.lat - lat, cell.lon - lng)
          if (distance < bestDistance) {
            bestDistance = distance
            best = cell
          }
        }

        let html = `位置 ${lat.toFixed(3)}, ${lng.toFixed(3)}`
        if (best && bestDistance <= meta.step * 1.5) {
          html += `<br/>SST ${empty(best.v, '°C')}`
          html += sp
            ? `<br/>${sp.name} 棲地適合度 ${suit(best.v, sp, meta.month)} / 100`
            : '<br/>綜合潛在漁場格點'
          if (best.u !== undefined && best.w !== undefined) {
            html += `<br/>海流 ${Math.hypot(best.u, best.w).toFixed(2)} m/s，${dirName(bearingDeg(best.u, best.w))}`
          }
        } else {
          html += '<br/>此位置沒有鄰近的浮標內插資料'
        }
        return html
      }

      if (timeMode === 'past' && hires) {
        const { meta, lat: lats, lon: lons, layers } = hires
        let bestIndex = -1
        let bestDistance = Infinity
        for (let i = 0; i < lats.length; i++) {
          const distance = Math.abs(lats[i] - lat) + Math.abs(lons[i] - lng)
          if (distance < bestDistance) {
            bestDistance = distance
            bestIndex = i
          }
        }

        let html = `位置 ${lat.toFixed(3)}, ${lng.toFixed(3)}`
        if (bestIndex >= 0 && bestDistance <= meta.step * 2 && layers.sst[bestIndex] != null) {
          html += `<br/>SST ${layers.sst[bestIndex]}°C`
          if (layers.chl?.[bestIndex] != null) {
            html += `<br/>葉綠素 ${layers.chl[bestIndex]} mg/m³`
          }
          if (layers.front?.[bestIndex] != null) {
            html += `<br/>海溫鋒面 ${layers.front[bestIndex]}`
          }
          const c = layers.conf?.[bestIndex]
          if (c != null) html += `<br/>資料信心 ${c}（${confLabel(c)}）`

          const allKeys = [
            ...meta.thermal.map((name) => 'T:' + name),
            ...meta.sdm.map((item) => 'S:' + item.name),
          ].filter((key) => layers[key])
          const selectedKeys = resolveHiresKeys(layers, species)
          const keys =
            baseField === 'habitat' && selectedKeys.length ? selectedKeys : allKeys
          const lines = keys
            .map((key) => {
              const value = layers[key]?.[bestIndex]
              if (value == null) return null
              return `${key.slice(2)}${key[0] === 'S' ? ' (SDM)' : ''} ${value}`
            })
            .filter(Boolean)
            .slice(0, 8)
          if (lines.length) html += '<br/>棲地適合度：' + lines.join(' / ')
        } else {
          html += '<br/>此位置沒有高解析格點資料'
        }
        return html
      }

      return null
    },
    [timeMode, baseField, leadIndex, species, forecast, fishing, hires, nowGrid],
  )
}
