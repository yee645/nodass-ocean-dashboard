import { useMemo } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { useFishingData } from '@/data/useData'
import type { FishCell, Station } from '@/data/contracts'

const IDW_RADIUS = 120 // km，與後端一致

function haversineKm(a: number, b: number, c: number, d: number): number {
  const R = 6371
  const p = Math.PI / 180
  const u =
    Math.sin(((c - a) * p) / 2) ** 2 +
    Math.cos(a * p) * Math.cos(c * p) * Math.sin(((d - b) * p) / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(u))
}

/** 以各站某時刻 SST，IDW 重算單一網格點（與後端同公式）。 */
function idwSST(
  lat: number,
  lon: number,
  vals: (number | null)[],
  stations: Station[],
): number | null {
  let num = 0
  let den = 0
  let near = 1e9
  for (let k = 0; k < stations.length; k++) {
    const v = vals[k]
    if (v == null) continue
    const d = haversineKm(lat, lon, stations[k].lat, stations[k].lon)
    if (d < near) near = d
    if (d <= IDW_RADIUS) {
      const w = 1 / (d * d + 1)
      num += w * v
      den += w
    }
  }
  return den > 0 && near <= IDW_RADIUS ? num / den : null
}

/**
 * 現在時段網格：依 nowTimeIndex 以各站該時刻 SST 重算 v（u/w/tr 不變）。
 * 對應 fishing.py 的 setTime()，達成時間軸逐時回放。
 */
export function useNowGrid(): { grid: FishCell[] | null; timeIndex: number } {
  const nowTimeIndex = useAppStore((s) => s.nowTimeIndex)
  const { data: fishing } = useFishingData()

  return useMemo(() => {
    if (!fishing) return { grid: null, timeIndex: 0 }
    const { grid, stations, times } = fishing
    if (!times.length) return { grid, timeIndex: 0 }
    const i = Math.max(0, Math.min(times.length - 1, nowTimeIndex))
    const vals = stations.map((s) => (s.sst_t ? s.sst_t[i] : null))
    const recomputed = grid.map((c) => {
      const v = idwSST(c.lat, c.lon, vals, stations)
      return { ...c, v: v == null ? null : Math.round(v * 100) / 100 }
    })
    return { grid: recomputed, timeIndex: i }
  }, [fishing, nowTimeIndex])
}
