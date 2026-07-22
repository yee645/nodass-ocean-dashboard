/**
 * 第一層/第二層額外資料載入（魚種出現點、漁港起點）。
 * 沿用 useData.ts 的 react-query + BASE_URL/data 慣例；獨立新檔，不改同學 useData.ts。
 * 資料來源：sdm/occurrences_web.json、sdm/ports.json（由 sync_web_data.py 同步進 public/data）。
 */
import { useQuery } from '@tanstack/react-query'

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
