/**
 * 第一層/第二層額外資料載入（魚種出現點、漁港起點）。
 * 沿用 useData.ts 的 react-query + BASE_URL/data 慣例；獨立新檔，不改同學 useData.ts。
 * 資料來源：sdm/occurrences_web.json、sdm/ports.json（由 sync_web_data.py 同步進 public/data）。
 */
import { useQuery } from '@tanstack/react-query'
import type { SdmNowPayload } from './contracts'

const asset = (name: string): string => `${import.meta.env.BASE_URL}data/${name}`

async function fetchJson<T>(name: string): Promise<T> {
  const res = await fetch(asset(name))
  if (!res.ok) throw new Error(`載入 ${name} 失敗：${res.status}`)
  return res.json() as Promise<T>
}

/** 出現點精簡格式：s=魚種名, lat/lon, m=月份。供第一層 KDE。 */
export interface OccRaw {
  s: string
  lat: number
  lon: number
  m: number
}

/** 漁港起點：第二層 A* 出發點。 */
export interface Port {
  name: string
  kind: string
  county: string
  lat: number
  lon: number
}

/** 水深格點（build_bathymetry.py，GEBCO 重取樣）：第二層吃水限制用。 */
export interface BathymetryCell {
  lat: number
  lon: number
  depth: number // 正值水深(公尺)
}
export interface BathymetryPayload {
  step: number
  cells: BathymetryCell[]
}

/** 漁業資源保育區（fetch_conservation_zones.py 解析）：第二層避開區域。 */
export interface RestrictedZone {
  name: string
  county: string
  level: string
  polygon: [number, number][] // [lon, lat] 環
}

/** 潮汐測站（fetch_tide.py）：第二層水深門檻的單點潮位修正用。 */
export interface TideStation {
  name: string
  lat: number
  lon: number
  tideM: number // 目前潮位(公尺，相對平均海平面，可正可負)
}

/** 魚種出現點（第一層 occurrenceDensity/confidence 用）。 */
export function useOccurrences() {
  return useQuery({
    queryKey: ['occurrences_web'],
    queryFn: () => fetchJson<OccRaw[]>('occurrences_web.json'),
  })
}

/** 漁港起點清單（第二層航線規劃用）。 */
export function usePorts() {
  return useQuery({
    queryKey: ['ports'],
    queryFn: () => fetchJson<Port[]>('ports.json'),
  })
}

/** 水深格點（第二層吃水限制用）。 */
export function useBathymetry() {
  return useQuery({
    queryKey: ['bathymetry'],
    queryFn: () => fetchJson<BathymetryPayload>('bathymetry.json'),
  })
}

/** 漁業資源保育區清單（第二層避開區域用）。 */
export function useRestrictedZones() {
  return useQuery({
    queryKey: ['restricted_zones'],
    queryFn: () => fetchJson<RestrictedZone[]>('restricted_zones.json'),
  })
}

/** 潮汐測站清單（第二層水深潮位修正用）；資料尚未產生時 sync 會略過，query 回傳空陣列。 */
export function useTide() {
  return useQuery({
    queryKey: ['tide'],
    queryFn: () => fetchJson<TideStation[]>('tide.json'),
    retry: false,
  })
}

/** 第一層 ML SDM 係數(issue #10)：氣候場多協變數模型，取代弱版即時快照。查無資料時 query 回傳 undefined，
 * 呼叫端(hotspotLayers.ts)須 fallback 回規則式 nowMath.suit()，零回歸。 */
export function useSdmNow() {
  return useQuery({
    queryKey: ['sdm_now'],
    queryFn: () => fetchJson<SdmNowPayload>('sdm_now.json'),
    retry: false,
  })
}

/** 找離指定座標最近的潮汐測站，回傳目前潮位(公尺)；無資料時回傳 0(不修正)。 */
export function nearestTideM(stations: TideStation[] | undefined, lat: number, lon: number): number {
  if (!stations || stations.length === 0) return 0
  let best = stations[0]
  let bd = Infinity
  for (const st of stations) {
    const d = (st.lat - lat) ** 2 + (st.lon - lon) ** 2
    if (d < bd) {
      bd = d
      best = st
    }
  }
  return best.tideM
}
