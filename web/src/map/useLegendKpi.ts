import { useMemo } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { useForecastData } from '@/data/useData'
import { FIELD_CFG, LOWCONF } from './layers/fieldConfig'
import type { PaletteName } from './palettes'

export interface LegendKpi {
  available: boolean
  fieldLabel: string
  palette: PaletteName
  lohiNote: string
  kpi: [string, string][]
}

const EMPTY: LegendKpi = {
  available: false,
  fieldLabel: '',
  palette: 'jet',
  lohiNote: '',
  kpi: [],
}

/** 圖例與 KPI（移植 build_forecast.py 的 draw/drawHabitat 統計與 setLegend）。 */
export function useLegendKpi(): LegendKpi {
  const timeMode = useAppStore((s) => s.timeMode)
  const baseField = useAppStore((s) => s.baseField)
  const leadIndex = useAppStore((s) => s.leadIndex)
  const species = useAppStore((s) => s.species)
  const { data: forecast } = useForecastData()

  return useMemo<LegendKpi>(() => {
    if (timeMode !== 'future' || !forecast) return EMPTY
    const { meta, chl, conf, data } = forecast
    const li = Math.max(0, Math.min(meta.leads.length - 1, leadIndex))
    const lead = meta.leads[li]
    const D = data[String(lead.d)]
    if (!D) return EMPTY
    const cfg = FIELD_CFG[baseField]
    const valid = lead.valid.slice(5, 16)

    // 棲地：逐格取所選魚種最大值
    if (baseField === 'habitat') {
      const keys = species
      if (!keys.length) {
        return {
          available: true,
          fieldLabel: '棲地適合度',
          palette: 'jet',
          lohiNote: '',
          kpi: [['提示', '請勾選魚種']],
        }
      }
      let n = 0
      let sum = 0
      let mx = 0
      const len = D.sst.length
      for (let i = 0; i < len; i++) {
        let best: number | null = null
        for (const nm of keys) {
          const arr = D.s[nm]
          if (!arr) continue
          const v = arr[i]
          if (v != null && (best == null || v > best)) best = v
        }
        if (best == null) continue
        n++
        sum += best
        if (best > mx) mx = best
      }
      return {
        available: true,
        fieldLabel: keys.length > 1 ? '最適魚種棲地(複選取最大值)' : '棲地適合度',
        palette: 'jet',
        lohiNote: '',
        kpi: [
          ['預報時刻', valid],
          ['選取魚種', String(keys.length)],
          ['平均', n ? (sum / n).toFixed(0) : '—'],
          ['最高', String(mx)],
        ],
      }
    }

    const arr =
      baseField === 'chl'
        ? chl
        : baseField === 'conf'
          ? conf
          : (D as unknown as Record<string, (number | null)[]>)[baseField]

    let n = 0
    let sum = 0
    let mn = Infinity
    let mx = -Infinity
    let low = 0
    for (const v of arr) {
      if (v == null) continue
      n++
      sum += v
      if (v < mn) mn = v
      if (v > mx) mx = v
      if (v < LOWCONF) low++
    }
    const avg = n ? sum / n : 0

    let kpi: [string, string][]
    let lohiNote = ''
    if (baseField === 'ws') {
      kpi = [
        ['預報時刻', valid],
        ['風速範圍', `${mn.toFixed(2)}~${mx.toFixed(2)} m/s`],
        ['平均', `${avg.toFixed(2)} m/s`],
        ['模式', 'OCM 地面風'],
      ]
      lohiNote = `相對色階 ${mn.toFixed(2)}–${mx.toFixed(2)} m/s（絕對風力以氣象署強風特報為準）`
    } else if (baseField === 'wl') {
      kpi = [
        ['預報時刻', valid],
        ['潮位範圍', `${mn.toFixed(2)}~${mx.toFixed(2)} m`],
        ['平均', `${avg.toFixed(2)} m`],
      ]
      lohiNote = '低潮 ← 0 → 高潮'
    } else if (baseField === 'conf') {
      kpi = [
        ['網格數', String(n)],
        ['平均信心', avg.toFixed(2)],
        ['低信心格', String(low)],
        ['門檻', `<${LOWCONF}`],
      ]
      lohiNote = '資料信心 0低 → 1高'
    } else {
      kpi = [
        ['預報時刻', valid],
        ['解析度', '~5km'],
        ['平均', avg.toFixed(2)],
        ['最高', mx.toFixed(2)],
      ]
    }

    return {
      available: true,
      fieldLabel: cfg.label + (baseField === 'chl' ? '(靜態)' : ''),
      palette: cfg.pal,
      lohiNote,
      kpi,
    }
  }, [timeMode, baseField, leadIndex, species, forecast])
}
