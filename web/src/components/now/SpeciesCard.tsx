import { useAppStore } from '@/store/useAppStore'
import { useFishingData } from '@/data/useData'
import { bearingDeg, dirName } from '@/map/layers/nowMath'

const fmt = (value: number | undefined, digits = 1): string =>
  value == null ? '-' : value.toFixed(digits)

export default function SpeciesCard() {
  const species = useAppStore((s) => s.species)
  const { data: fishing } = useFishingData()
  if (!fishing) return null

  const cur = species.length ? species[0] : null
  if (!cur) return null

  const sp = fishing.species.find((item) => item.name === cur)
  if (!sp) return null

  const month = fishing.meta.month
  const inSeason = sp.season.includes(month)
  const currentCells = fishing.grid.filter(
    (cell) => cell.u !== undefined && cell.w !== undefined,
  )
  const trendCells = fishing.grid.filter((cell) => cell.tr !== undefined)
  const avgTrend = trendCells.length
    ? trendCells.reduce((sum, cell) => sum + (cell.tr as number), 0) /
      trendCells.length
    : null
  const avgFront = fishing.stations.length
    ? fishing.stations.reduce((sum, station) => sum + station.front, 0) /
      fishing.stations.length
    : null

  let currentText = '海流資料不足'
  if (currentCells.length) {
    const avgU =
      currentCells.reduce((sum, cell) => sum + (cell.u as number), 0) /
      currentCells.length
    const avgW =
      currentCells.reduce((sum, cell) => sum + (cell.w as number), 0) /
      currentCells.length
    currentText = `${dirName(bearingDeg(avgU, avgW))} ${Math.hypot(avgU, avgW).toFixed(2)} m/s`
  }

  const weights = sp.weights ?? {}

  return (
    <div className="border-t border-border pt-2">
      <h3 className="type-card-title mb-1.5">
        {sp.name} - {sp.en}
      </h3>

      <div className="type-control grid grid-cols-2 gap-x-3 gap-y-1 leading-[1.55] text-ink">
        <div>
          適溫 <b className="text-[#ffd166]">{sp.opt_lo}-{sp.opt_hi}°C</b>
        </div>
        <div className="text-right text-muted">範圍 {sp.sst_min}-{sp.sst_max}°C</div>
        <div>
          鋒面偏好 <b className="text-[#9fd3ff]">{fmt(sp.front_opt)}</b>
        </div>
        <div className="text-right text-muted">目前 {fmt(avgFront ?? undefined)}</div>
        <div>
          流速偏好 <b className="text-[#9fd3ff]">{fmt(sp.current_opt, 2)} m/s</b>
        </div>
        <div className="text-right text-muted">目前 {currentText}</div>
      </div>

      <div className="type-control mt-1.5 leading-[1.55] text-muted">
        季節 {sp.season.join(', ')} 月，
        <b className={inSeason ? 'text-[#49c57f]' : 'text-[#f0a202]'}>
          {inSeason ? '目前在主要季節' : '目前非主要季節'}
        </b>
        。近兩日 SST 趨勢 {avgTrend == null ? '-' : `${avgTrend > 0 ? '+' : ''}${avgTrend.toFixed(3)}°C/hr`}。
      </div>

      <div className="type-control mt-1.5 leading-[1.55] text-muted">
        棲地 {sp.region}，水層 {sp.depth}。{sp.habit}
      </div>

      {sp.signals?.length ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {sp.signals.map((signal) => (
            <span
              key={signal}
              className="type-caption rounded-[12px] border border-border-strong bg-surface px-2 py-0.5 text-[#cfe0f5]"
            >
              {signal}
            </span>
          ))}
        </div>
      ) : null}

      <div className="type-caption mt-1.5 text-muted">
        計分權重：海溫 {Math.round((weights.sst ?? 0.6) * 100)}%、鋒面{' '}
        {Math.round((weights.front ?? 0.15) * 100)}%、流速{' '}
        {Math.round((weights.current ?? 0.1) * 100)}%、季節{' '}
        {Math.round((weights.season ?? 0.15) * 100)}%。
      </div>
    </div>
  )
}
