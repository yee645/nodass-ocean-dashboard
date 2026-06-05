import type { TimeMode } from '@/store/useAppStore'

export interface ModeMeta {
  key: TimeMode
  label: string
  hint: string
}

/** 三時段中繼資料（對應舊 platform.html 的 MODES）。 */
export const MODES: ModeMeta[] = [
  {
    key: 'past',
    label: '過去 · 高解析衛星',
    hint: '衛星 ~4km 海溫/葉綠素/鋒面與資料驅動 SDM（空間交叉驗證 AUC）',
  },
  {
    key: 'now',
    label: '現在 · 即時浮標',
    hint: '即時浮標海溫與魚種棲地、魚群熱區與漂移、近兩日時間軸回放',
  },
  {
    key: 'future',
    label: '未來 · CWA 預報',
    hint: '氣象署 OCM 未來數日海象(風/流/潮)+葉綠素，多魚種棲地與信心圖層',
  },
]

export const modeByKey = (key: TimeMode): ModeMeta =>
  MODES.find((m) => m.key === key) ?? MODES[1]
