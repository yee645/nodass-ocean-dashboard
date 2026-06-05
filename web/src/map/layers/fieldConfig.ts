import type { BaseField } from '@/store/useAppStore'
import type { PaletteName } from '../palettes'

export interface FieldCfg {
  /** 色階下界；null 表依當前資料動態縮放（對應舊 BASE 第3欄）。 */
  lo: number | null
  hi: number | null
  log: boolean
  pal: PaletteName
  label: string
}

// 1:1 對應 build_forecast.py 的 BASE 設定。
export const FIELD_CFG: Record<BaseField, FieldCfg> = {
  sst: { lo: 18, hi: 30, log: false, pal: 'jet', label: '海溫 SST (°C)' },
  cspd: { lo: 0, hi: 1.5, log: false, pal: 'jet', label: '海流速 (m/s)' },
  ws: { lo: null, hi: null, log: false, pal: 'wind', label: '風速 (m/s，模式場)' },
  wl: { lo: -1.2, hi: 1.2, log: false, pal: 'tide', label: '潮位 (m)' },
  conf: { lo: 0, hi: 1, log: false, pal: 'conf', label: '資料信心(出現點支持)' },
  chl: { lo: -1.3, hi: 0.5, log: true, pal: 'jet', label: '葉綠素氣候平均 (mg/m³)' },
  front: { lo: 0, hi: 1.2, log: false, pal: 'jet', label: '海溫鋒面強度' },
  habitat: { lo: 0, hi: 100, log: false, pal: 'jet', label: '棲地適合度(選魚種)' },
}

export const LOWCONF = 0.3
