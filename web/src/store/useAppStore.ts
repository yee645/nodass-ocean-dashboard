import { create } from 'zustand'

/** 三個時段：過去(衛星高解析)/現在(即時浮標)/未來(CWA 預報)。 */
export type TimeMode = 'past' | 'now' | 'future'

/** 互斥底層純量場（一次只開一個）。habitat 才顯示魚種複選。
 *  cspd/ws/wl 屬未來；front 屬過去；sst/chl/conf/habitat 共用。 */
export type BaseField =
  | 'sst'
  | 'cspd'
  | 'ws'
  | 'wl'
  | 'conf'
  | 'chl'
  | 'front'
  | 'habitat'

/** 各時段可用的 base 欄位白名單（切時段時據此保留/重設選擇，避免衝突）。 */
export const BASE_WHITELIST: Record<TimeMode, BaseField[]> = {
  future: ['sst', 'cspd', 'ws', 'wl', 'conf', 'chl', 'habitat'],
  past: ['sst', 'chl', 'front', 'conf', 'habitat'],
  now: [], // now 不使用 baseField（改用魚種單選）
}

/** 可混用 overlay（複選，互不影響）。 */
export interface Overlays {
  current: boolean // 海流向量
  wind: boolean // 風向量
  occurrence: boolean // 物種出現點
  buoy: boolean // 浮標站點
}

interface AppState {
  timeMode: TimeMode
  baseField: BaseField
  overlays: Overlays
  species: string[] // 跨時段共享的魚種選擇(取代舊 postMessage)
  leadIndex: number // 未來時段預報時間軸索引
  nowTimeIndex: number // 現在時段時間軸索引(大值→由 hook 夾到最新)
  playing: boolean
  confDim: boolean // 低信心淡化(修飾子，非獨立圖層)
  fishMove: boolean // 現在時段：魚群熱區與漂移
  selectedStationId: string | null // 現在時段：點選的浮標(時序圖)
  leftPanelOpen: boolean
  layerPanelCollapsed: boolean

  setTimeMode: (m: TimeMode) => void
  setBaseField: (f: BaseField) => void
  toggleOverlay: (k: keyof Overlays) => void
  setSpecies: (s: string[]) => void
  setLeadIndex: (i: number) => void
  setNowTimeIndex: (i: number) => void
  setPlaying: (p: boolean) => void
  setConfDim: (b: boolean) => void
  setFishMove: (b: boolean) => void
  setSelectedStation: (id: string | null) => void
  setLeftPanelOpen: (b: boolean) => void
  toggleLayerPanel: () => void
}

export const useAppStore = create<AppState>((set) => ({
  timeMode: 'now', // 預設「現在」(即時浮標)，與舊 platform 一致
  baseField: 'sst',
  overlays: { current: true, wind: false, occurrence: false, buoy: true },
  species: [],
  leadIndex: 0,
  nowTimeIndex: 1e9, // 預設最新時刻(由 useNowGrid 夾到 times.length-1)
  playing: false,
  confDim: false,
  fishMove: true,
  selectedStationId: null,
  leftPanelOpen: true,
  layerPanelCollapsed: false,

  // 切時段：base 欄位不在新時段白名單時重設為 sst（保留仍適用者）。
  setTimeMode: (timeMode) =>
    set((s) => {
      const wl = BASE_WHITELIST[timeMode]
      const baseField =
        timeMode === 'now' || wl.includes(s.baseField) ? s.baseField : 'sst'
      return { timeMode, baseField, playing: false }
    }),
  setBaseField: (baseField) => set({ baseField }),
  toggleOverlay: (k) =>
    set((s) => ({ overlays: { ...s.overlays, [k]: !s.overlays[k] } })),
  setSpecies: (species) => set({ species }),
  setLeadIndex: (leadIndex) => set({ leadIndex }),
  setNowTimeIndex: (nowTimeIndex) => set({ nowTimeIndex }),
  setPlaying: (playing) => set({ playing }),
  setConfDim: (confDim) => set({ confDim }),
  setFishMove: (fishMove) => set({ fishMove }),
  setSelectedStation: (selectedStationId) => set({ selectedStationId }),
  setLeftPanelOpen: (leftPanelOpen) => set({ leftPanelOpen }),
  toggleLayerPanel: () =>
    set((s) => ({ layerPanelCollapsed: !s.layerPanelCollapsed })),
}))
