import { useAppStore } from '@/store/useAppStore'
import { useFishingData } from '@/data/useData'
import { bearingDeg, dirName } from '@/map/layers/nowMath'

export default function SpeciesCard() {
  const species = useAppStore((s) => s.species)
  const { data: fishing } = useFishingData()
  if (!fishing) return null
  const cur = species.length ? species[0] : null
  if (!cur) return null
  const sp = fishing.species.find((s) => s.name === cur)
  if (!sp) return null

  const month = fishing.meta.month
  const inSeason = sp.season.includes(month)

  const grid = fishing.grid
  const trends = grid
    .filter((c) => c.tr !== undefined)
    .map((c) => c.tr as number)
  const avgTrend = trends.length
    ? trends.reduce((sum, value) => sum + value, 0) / trends.length
    : 0
  const currentCells = grid.filter((c) => c.u !== undefined && c.w !== undefined)
  let currentText = '海流資料不足'
  if (currentCells.length) {
    const avgU = currentCells.reduce((sum, c) => sum + (c.u as number), 0) / currentCells.length
    const avgW = currentCells.reduce((sum, c) => sum + (c.w as number), 0) / currentCells.length
    currentText = `平均海流 ${dirName(bearingDeg(avgU, avgW))}，${Math.hypot(avgU, avgW).toFixed(2)} m/s`
  }

  const warmSpecies = (sp.opt_lo + sp.opt_hi) / 2 >= 23
  const shiftText =
    avgTrend > 0.02
      ? warmSpecies
        ? '暖水型魚種可能往北或外海擴張'
        : '冷水型魚種適棲區可能收縮'
      : avgTrend < -0.02
        ? warmSpecies
          ? '暖水型魚種適棲區可能南移或縮小'
          : '冷水型魚種可能往南或近岸延伸'
        : '水溫變化平穩，棲地位置以局部海流影響為主'

  return (
    <div className="border-t border-border pt-2">
      <h3 className="mb-1.5 text-[clamp(0.9rem,1.4vw,1rem)]">
        {sp.name} - {sp.en} - {sp.sci}
      </h3>
      <div className="text-[0.82rem] leading-[1.7]">
        <div>
          適溫窗：
          <b className="text-[#ffd166]">
            {sp.opt_lo}-{sp.opt_hi}°C
          </b>
          （耐受 {sp.sst_min}-{sp.sst_max}°C）
        </div>
        <div>
          旺季月份：{sp.season.join(', ')}；目前：
          <b style={{ color: inSeason ? '#2e933c' : '#f0a202' }}>
            {inSeason ? '旺季' : '非旺季'}
          </b>
        </div>
        <div>
          常見海域：{sp.region}；水深：{sp.depth}
        </div>
        <div className="mt-1">習性：{sp.habit}</div>
      </div>
      <div className="mt-1.5 text-[0.82rem] text-[#9fd3ff]">
        漂移判讀：{currentText}；近 6 小時水溫趨勢 {avgTrend > 0 ? '+' : ''}
        {avgTrend.toFixed(3)}°C/hr，{shiftText}
      </div>
    </div>
  )
}
