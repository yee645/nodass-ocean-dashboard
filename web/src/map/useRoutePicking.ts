import { useCallback } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { useCoast } from '@/data/useData'
import { nearestSeaPosition } from './layers/coastMask'

/** 航線起訖點的地圖點擊選取：routePicking 開啟時攔截點擊、吸附最近海面格，不彈 popup。 */
export function useRoutePicking(): (lng: number, lat: number) => boolean {
  const routePicking = useAppStore((s) => s.routePicking)
  const setRouteStart = useAppStore((s) => s.setRouteStart)
  const setRouteEnd = useAppStore((s) => s.setRouteEnd)
  const setRoutePicking = useAppStore((s) => s.setRoutePicking)
  const { data: coast } = useCoast()

  return useCallback(
    (lng, lat) => {
      if (!routePicking) return false
      const snapped = nearestSeaPosition(lng, lat, coast)
      if (snapped) {
        const point = { lon: snapped[0], lat: snapped[1] }
        if (routePicking === 'start') setRouteStart(point)
        else setRouteEnd(point)
      }
      setRoutePicking(null)
      return true
    },
    [routePicking, coast, setRouteStart, setRouteEnd, setRoutePicking],
  )
}
