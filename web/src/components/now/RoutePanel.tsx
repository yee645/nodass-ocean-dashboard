import { useMemo, useState } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { useFishingData, useCoast } from '@/data/useData'
import { usePorts, useBathymetry, useRestrictedZones, type Port } from '@/data/useExtras'
import { buildRouteCells } from '@/map/route/routeCells'
import { buildCostField, type Objective } from '@/map/route/costGrid'
import { astar } from '@/map/route/astar'

const OBJECTIVES: { key: Objective; label: string }[] = [
  { key: 'fish', label: '最高魚場' },
  { key: 'short', label: '最短距離' },
  { key: 'safe', label: '最安全(避浪/逆流)' },
  { key: 'fuel', label: '低油耗' },
]

const KM_PER_NM = 1.852

/** 第二層：航線規劃（現在時段）。起訖點 + 目標 + 吃水/續航/保育區限制 → A* 畫航線。 */
export default function RoutePanel() {
  const species = useAppStore((s) => s.species)
  const routePicking = useAppStore((s) => s.routePicking)
  const setRoutePicking = useAppStore((s) => s.setRoutePicking)
  const routeStart = useAppStore((s) => s.routeStart)
  const setRouteStart = useAppStore((s) => s.setRouteStart)
  const routeEnd = useAppStore((s) => s.routeEnd)
  const routeObjective = useAppStore((s) => s.routeObjective)
  const setRouteObjective = useAppStore((s) => s.setRouteObjective)
  const routeMaxRangeNm = useAppStore((s) => s.routeMaxRangeNm)
  const setRouteMaxRangeNm = useAppStore((s) => s.setRouteMaxRangeNm)
  const routeDraftM = useAppStore((s) => s.routeDraftM)
  const setRouteDraftM = useAppStore((s) => s.setRouteDraftM)
  const routeAvoidZones = useAppStore((s) => s.routeAvoidZones)
  const setRouteAvoidZones = useAppStore((s) => s.setRouteAvoidZones)
  const routeResult = useAppStore((s) => s.routeResult)
  const setRouteResult = useAppStore((s) => s.setRouteResult)

  const [speedKt, setSpeedKt] = useState(8)
  const [geoError, setGeoError] = useState<string | null>(null)

  const { data: fishing } = useFishingData()
  const { data: coast } = useCoast()
  const { data: ports } = usePorts()
  const { data: bathymetry } = useBathymetry()
  const { data: zones } = useRestrictedZones()

  const portsByCounty = useMemo(() => {
    const map = new Map<string, Port[]>()
    for (const p of ports ?? []) {
      const list = map.get(p.county) ?? []
      list.push(p)
      map.set(p.county, list)
    }
    return map
  }, [ports])

  if (!fishing) return null

  const curSpeciesName = species.length ? species[0] : null
  const curSpecies = fishing.species.find((s) => s.name === curSpeciesName) ?? null

  const useMyLocation = (): void => {
    setGeoError(null)
    if (!navigator.geolocation) {
      setGeoError('瀏覽器不支援定位')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setRouteStart({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => setGeoError('無法取得定位，請改用漁港選單'),
      { timeout: 8000 },
    )
  }

  const plan = (): void => {
    if (!routeStart || !routeEnd) return
    const cells = buildRouteCells({
      grid: fishing.grid,
      month: fishing.meta.month,
      species: curSpecies,
      coast,
      bathymetry,
      zones,
      draftM: routeDraftM,
      avoidZones: routeAvoidZones,
    })
    const cost = buildCostField(cells, routeObjective)
    const result = astar({
      cells,
      step: fishing.meta.step,
      cost,
      start: routeStart,
      goal: routeEnd,
    })
    setRouteResult(result)
  }

  const distanceNm = routeResult ? routeResult.lengthKm / KM_PER_NM : null
  const overRange =
    distanceNm != null && routeMaxRangeNm != null && distanceNm > routeMaxRangeNm

  return (
    <div className="border-t border-border pt-2">
      <div className="type-section-title mb-1 text-muted">航線規劃（第二層）</div>

      <div className="flex flex-col gap-1.5">
        <div>
          <label className="type-control mb-1 block text-muted">起點</label>
          <div className="flex gap-1.5">
            <select
              className="type-control flex-1 rounded-lg border border-border-strong bg-surface px-2 py-1 text-ink"
              value=""
              onChange={(e) => {
                const p = (ports ?? []).find((x) => x.name === e.target.value)
                if (p) setRouteStart({ lat: p.lat, lon: p.lon })
              }}
            >
              <option value="">選擇漁港...</option>
              {Array.from(portsByCounty.entries()).map(([county, list]) => (
                <optgroup key={county} label={county}>
                  {list.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <button
              onClick={useMyLocation}
              title="使用目前定位"
              className="type-control shrink-0 cursor-pointer rounded-lg border border-border-strong bg-surface px-2 py-1 text-muted hover:border-accent hover:text-white"
            >
              定位
            </button>
          </div>
          {routeStart && (
            <div className="type-caption mt-0.5 text-muted">
              {routeStart.lat.toFixed(3)}, {routeStart.lon.toFixed(3)}
            </div>
          )}
          {geoError && (
            <div className="type-caption mt-0.5 text-[#ff6b6b]">{geoError}</div>
          )}
        </div>

        <div>
          <label className="type-control mb-1 block text-muted">終點</label>
          <button
            onClick={() => setRoutePicking(routePicking === 'end' ? null : 'end')}
            className={
              'type-control w-full cursor-pointer rounded-lg border px-3 py-1.5 text-left ' +
              (routePicking === 'end'
                ? 'border-accent bg-accent font-semibold text-white'
                : 'border-border-strong bg-surface text-muted hover:text-ink')
            }
          >
            {routePicking === 'end' ? '請在地圖上點選終點...' : '在地圖上點選終點'}
          </button>
          {routeEnd && (
            <div className="type-caption mt-0.5 text-muted">
              {routeEnd.lat.toFixed(3)}, {routeEnd.lon.toFixed(3)}
            </div>
          )}
        </div>

        <div>
          <div className="type-control mb-1 text-muted">目標（單選）</div>
          <div className="flex flex-col gap-1">
            {OBJECTIVES.map((o) => (
              <button
                key={o.key}
                onClick={() => setRouteObjective(o.key)}
                className={
                  'type-control cursor-pointer rounded-lg border px-3 py-1.5 text-left ' +
                  (routeObjective === o.key
                    ? 'border-accent bg-accent font-semibold text-white'
                    : 'border-border-strong bg-surface text-muted hover:text-ink')
                }
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <label className="type-control text-muted">
            吃水限制(m)
            <input
              type="number"
              min={0}
              step={0.5}
              value={routeDraftM}
              onChange={(e) => setRouteDraftM(Math.max(0, Number(e.target.value)))}
              className="mt-0.5 w-full rounded-lg border border-border-strong bg-surface px-2 py-1 text-ink"
            />
          </label>
          <label className="type-control text-muted">
            最大續航(浬)
            <input
              type="number"
              min={0}
              placeholder="不限"
              value={routeMaxRangeNm ?? ''}
              onChange={(e) =>
                setRouteMaxRangeNm(e.target.value === '' ? null : Number(e.target.value))
              }
              className="mt-0.5 w-full rounded-lg border border-border-strong bg-surface px-2 py-1 text-ink"
            />
          </label>
        </div>

        <label className="type-control flex cursor-pointer items-center gap-2 text-ink">
          <input
            type="checkbox"
            checked={routeAvoidZones}
            onChange={(e) => setRouteAvoidZones(e.target.checked)}
            className="h-4 w-4 rounded accent-accent"
          />
          避開漁業資源保育區
        </label>

        <label className="type-control flex items-center gap-2 text-muted">
          船速(節)
          <input
            type="number"
            min={1}
            value={speedKt}
            onChange={(e) => setSpeedKt(Math.max(1, Number(e.target.value)))}
            className="w-16 rounded-lg border border-border-strong bg-surface px-2 py-1 text-ink"
          />
        </label>

        <button
          onClick={plan}
          disabled={!routeStart || !routeEnd}
          className="type-control cursor-pointer rounded-lg border border-accent bg-accent px-3 py-1.5 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          規劃航線
        </button>

        {routeResult && distanceNm != null && (
          <div className="type-control rounded-lg border border-border-strong bg-panel-2 p-2 text-ink">
            距離 <b>{distanceNm.toFixed(1)} 浬</b> 預估航行時間{' '}
            <b>{(distanceNm / speedKt).toFixed(1)} 小時</b>
            {overRange && (
              <div className="type-caption mt-1 text-[#ff6b6b]">
                超出設定的最大續航範圍，僅供參考，請自行評估油料/補給。
              </div>
            )}
          </div>
        )}

        <div className="type-caption text-muted">
          航線僅在浮標覆蓋範圍(近岸)內規劃，未涵蓋軍事管制水域；漁業資源保育區座標為自動解析結果，可能有遺漏，正式航行請以官方公告為準。
        </div>
      </div>
    </div>
  )
}
