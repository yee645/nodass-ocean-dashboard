import { useQuery } from '@tanstack/react-query'
import type {
  CoastGeoJSON,
  FishingPayload,
  ForecastPayload,
  HiresPayload,
} from './contracts'

// base 對齊 Vite（dev='/', build='/nodass-ocean-dashboard/'），確保 GitHub Pages 路徑正確。
const asset = (name: string): string => `${import.meta.env.BASE_URL}data/${name}`

async function fetchJson<T>(name: string): Promise<T> {
  const res = await fetch(asset(name))
  if (!res.ok) throw new Error(`載入 ${name} 失敗：${res.status}`)
  return res.json() as Promise<T>
}

/** 未來時段：CWA OCM 預報網格。 */
export function useForecastData() {
  return useQuery({
    queryKey: ['forecast_grid'],
    queryFn: () => fetchJson<ForecastPayload>('forecast_grid.json'),
  })
}

/** 現在時段：即時浮標漁場棲地。 */
export function useFishingData() {
  return useQuery({
    queryKey: ['fishing_grid'],
    queryFn: () => fetchJson<FishingPayload>('fishing_grid.json'),
  })
}

/** 過去時段：衛星高解析棲地 + SDM + 信心。 */
export function useHiresData() {
  return useQuery({
    queryKey: ['hires_grid'],
    queryFn: () => fetchJson<HiresPayload>('hires_grid.json'),
  })
}

/** 陸地遮罩 GeoJSON（各時段共用）。 */
export function useCoast() {
  return useQuery({
    queryKey: ['region_coast'],
    queryFn: () => fetchJson<CoastGeoJSON>('region_coast.json'),
  })
}
