/** 對齊 Python 管線輸出的 JSON schema（build_forecast.py / build_hires.py）。 */

export interface Cell {
  lat: number
  lon: number
}

/** 單一預報時段的各場陣列（與 cells 同長、同索引）。 */
export interface LeadData {
  sst: (number | null)[]
  u: (number | null)[]
  w: (number | null)[]
  cspd: (number | null)[]
  ws: (number | null)[]
  wd: (number | null)[]
  wl: (number | null)[]
  /** 各魚種棲地適合度 0–100。 */
  s: Record<string, (number | null)[]>
}

export interface ForecastMeta {
  init: string
  bbox: [number, number, number, number] // [lonMin, lonMax, latMin, latMax]
  step: number
  month: number
  species: string[]
  leads: { d: number; valid: string }[]
  source: string
  has_conf: boolean
}

export interface ForecastPayload {
  meta: ForecastMeta
  cells: Cell[]
  chl: (number | null)[]
  conf: (number | null)[]
  data: Record<string, LeadData> // key = String(lead.d)
}

/** === 現在時段（fishing）schema（build_fishing.py） === */

export interface Species {
  name: string
  en: string
  sci: string
  sst_min: number
  opt_lo: number
  opt_hi: number
  sst_max: number
  season: number[]
  region: string
  depth: string
  habit: string
  front_opt?: number
  front_max?: number
  current_opt?: number
  current_max?: number
  temp_sigma?: number
  season_floor?: number
  weights?: {
    sst?: number
    front?: number
    current?: number
    season?: number
  }
  signals?: string[]
}

export interface Station {
  id: string
  name: string
  charge: string
  lat: number
  lon: number
  sst: number
  current: number | null
  u: number | null
  w: number | null
  trend: number | null
  sst_series: { t: string; v: number }[]
  front: number
  fish_score: number
  level: string
  color: string
  species: Record<string, number>
  sst_t: (number | null)[] // 對齊 times 的逐時 SST（前向填補）
}

/** 內插網格格點：v=SST、u/w=海流、tr=SST 趨勢。 */
export interface FishCell {
  lat: number
  lon: number
  v: number | null
  u?: number
  w?: number
  tr?: number
}

export interface FishingPayload {
  meta: { month: number; step: number; generated: string }
  species: Species[]
  stations: Station[]
  grid: FishCell[]
  times: string[]
}

/** === 過去時段（hires 衛星高解析）schema（build_hires.py） === */

export interface HiresMeta {
  bbox: [number, number, number, number]
  step: number
  window: [string, string]
  thermal: string[] // 適溫代理魚種名
  sdm: { name: string; n: number; auc: number | null; rauc: number | null }[]
  n_sst_valid: number
  has_conf: boolean
  source: string
}

/** 欄位式：lat/lon 與各 layer 同長同索引；layer key 含 sst/chl/front/conf 與 T:/S:魚種。 */
export interface HiresPayload {
  meta: HiresMeta
  lat: number[]
  lon: number[]
  layers: Record<string, (number | null)[]>
}

/** region_coast.json：陸地遮罩 GeoJSON（寬鬆定義，免依賴 @types/geojson 全域型別）。 */
export interface CoastFeature {
  type: 'Feature'
  properties: Record<string, unknown>
  geometry: {
    type: 'Polygon' | 'MultiPolygon'
    coordinates: number[][][] | number[][][][]
  }
}
export interface CoastGeoJSON {
  type: 'FeatureCollection'
  features: CoastFeature[]
}
