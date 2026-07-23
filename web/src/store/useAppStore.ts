import { create } from 'zustand'
import type { Objective } from '@/map/route/costGrid'
import type { RoutePoint, RouteResult } from '@/map/route/astar'

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

  // 第二層：航線規劃（現在時段）
  routePicking: 'start' | 'end' | 'waypoint' | null
  routeStart: RoutePoint | null
  routeEnd: RoutePoint | null
  routeWaypoints: RoutePoint[] // 起訖點之間的手動中繼站，依序規劃
  routeObjective: Objective
  routeMaxRangeNm: number | null // null = 不限
  routeDraftM: number // 0 = 不限
  routeAvoidZones: boolean
  routeSpeedKt: number // 船速(節)，估算 ETA 用
  routeShowDepth: boolean // 顯示水深參考圖層
  routeResult: RouteResult | null

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

  setRoutePicking: (p: 'start' | 'end' | 'waypoint' | null) => void
  setRouteStart: (p: RoutePoint | null) => void
  setRouteEnd: (p: RoutePoint | null) => void
  addRouteWaypoint: (p: RoutePoint) => void
  removeRouteWaypoint: (index: number) => void
  clearRouteWaypoints: () => void
  setRouteObjective: (o: Objective) => void
  setRouteMaxRangeNm: (nm: number | null) => void
  setRouteDraftM: (m: number) => void
  setRouteAvoidZones: (b: boolean) => void
  setRouteSpeedKt: (kt: number) => void
  setRouteShowDepth: (b: boolean) => void
  setRouteResult: (r: RouteResult | null) => void
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

  routePicking: null,
  routeStart: null,
  routeEnd: null,
  routeWaypoints: [],
  routeObjective: 'fish',
  routeMaxRangeNm: null,
  routeDraftM: 0,
  routeAvoidZones: true,
  routeSpeedKt: 8,
  routeShowDepth: false,
  routeResult: null,

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

  setRoutePicking: (routePicking) => set({ routePicking }),
  setRouteStart: (routeStart) => set({ routeStart }),
  setRouteEnd: (routeEnd) => set({ routeEnd }),
  addRouteWaypoint: (p) =>
    set((s) => ({ routeWaypoints: [...s.routeWaypoints, p] })),
  removeRouteWaypoint: (index) =>
    set((s) => ({ routeWaypoints: s.routeWaypoints.filter((_, i) => i !== index) })),
  clearRouteWaypoints: () => set({ routeWaypoints: [] }),
  setRouteObjective: (routeObjective) => set({ routeObjective }),
  setRouteMaxRangeNm: (routeMaxRangeNm) => set({ routeMaxRangeNm }),
  setRouteDraftM: (routeDraftM) => set({ routeDraftM }),
  setRouteAvoidZones: (routeAvoidZones) => set({ routeAvoidZones }),
  setRouteSpeedKt: (routeSpeedKt) => set({ routeSpeedKt }),
  setRouteShowDepth: (routeShowDepth) => set({ routeShowDepth }),
  setRouteResult: (routeResult) => set({ routeResult }),
}))
