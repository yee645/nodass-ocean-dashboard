import { useAppStore } from '@/store/useAppStore'
import { useFishingData } from '@/data/useData'
import SpeciesCard from './now/SpeciesCard'
import StationTable from './now/StationTable'
import SstChart from './now/SstChart'

const heatBar =
  'linear-gradient(90deg,rgb(46,147,108),rgb(240,162,2),rgb(215,38,61))'

export default function NowPanel() {
  const species = useAppStore((s) => s.species)
  const setSpecies = useAppStore((s) => s.setSpecies)
  const fishMove = useAppStore((s) => s.fishMove)
  const setFishMove = useAppStore((s) => s.setFishMove)
  const { data: fishing } = useFishingData()

  if (!fishing) return <div className="text-[0.8rem] text-muted">資料載入中...</div>
  const { stations, species: speciesOptions } = fishing
  const cur = species.length ? species[0] : null

  const valOf = (st: (typeof stations)[number]): number =>
    cur == null ? st.fish_score : (st.species[cur] ?? 0)
  const vals = stations.map(valOf)
  const hi = vals.filter((v) => v >= 60).length
  const ssts = stations.map((s) => s.sst)
  const maxV = vals.length ? Math.max(...vals) : 0
  const colorFor = (s: number): string =>
    s >= 60 ? '#d7263d' : s >= 35 ? '#f0a202' : '#2e933c'

  const select = (val: string | null) => setSpecies(val ? [val] : [])
  const chip = (label: string, val: string | null, on: boolean) => (
    <label
      key={val ?? 'overall'}
      onClick={(e) => {
        e.preventDefault()
        select(val)
      }}
      className={
        'flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-[14px] border px-2.5 py-1 text-[0.82rem] transition-colors ' +
        (on
          ? 'border-accent bg-accent text-white shadow-[0_0_0_1px_rgba(255,255,255,.08)_inset]'
          : 'border-border-strong bg-surface text-[#cdd9e5] hover:border-[#4d6f9f] hover:bg-[#223756]')
      }
    >
      <input type="radio" readOnly checked={on} className="accent-accent" />
      {label}
    </label>
  )

  return (
    <>
      <div>
        <div className="mb-1 text-[0.78rem] font-semibold text-muted">
          顯示（單選）
        </div>
        <div className="chip-scroll flex max-h-[142px] flex-wrap gap-1.5 overflow-auto rounded-lg border border-border bg-panel-2 p-1.5">
          {chip('綜合潛在漁場', null, cur == null)}
          {speciesOptions.map((sp) => chip(sp.name, sp.name, cur === sp.name))}
        </div>
      </div>

      <label className="flex cursor-pointer items-center gap-2 text-[0.82rem] text-ink">
        <input
          type="checkbox"
          checked={fishMove}
          onChange={(e) => setFishMove(e.target.checked)}
          className="h-4 w-4 rounded accent-accent"
        />
        魚群熱區與漂移
      </label>

      <div className="grid grid-cols-4 gap-2">
        <div className="rounded-md bg-surface px-2 py-2 text-center text-[0.78rem] text-muted">
          有效浮標
          <b className="block text-[clamp(1rem,1.8vw,1.25rem)] text-ink">{stations.length}</b>
        </div>
        <div className="rounded-md bg-surface px-2 py-2 text-center text-[0.78rem] text-muted">
          {'高分站(>=60)'}
          <b className="block text-[clamp(1rem,1.8vw,1.25rem)] text-[#ff3c63]">{hi}</b>
        </div>
        <div className="rounded-md bg-surface px-2 py-2 text-center text-[0.78rem] text-muted">
          SST範圍
          <b className="block text-[clamp(1rem,1.8vw,1.25rem)] text-ink">
            {Math.min(...ssts).toFixed(1)}-{Math.max(...ssts).toFixed(1)}
          </b>
        </div>
        <div className="rounded-md bg-surface px-2 py-2 text-center text-[0.78rem] text-muted">
          最高分
          <b
            className="block text-[clamp(1rem,1.8vw,1.25rem)]"
            style={{ color: colorFor(maxV) }}
          >
            {maxV.toFixed(1)}
          </b>
        </div>
      </div>

      <div className="text-[0.78rem] text-muted">
        {cur == null ? (
          <span>
            潛在漁場指標：
            <span className="ml-2 inline-block h-3 w-3 rounded-full bg-[#2e933c]" />低
            <span className="ml-2 inline-block h-3 w-3 rounded-full bg-[#f0a202]" />中
            <span className="ml-2 inline-block h-3 w-3 rounded-full bg-[#d7263d]" />高
          </span>
        ) : (
          <span>
            棲地適合度：
            <span
              className="mx-1 inline-block h-2.5 w-20 rounded-[3px] align-middle"
              style={{ background: heatBar }}
            />
            低-高
            <span className="ml-2 inline-block h-2.5 w-3.5 rounded-[2px] border-[1.5px] border-[#ffd000] bg-[rgba(255,208,0,.18)] align-middle" />
            適溫窗
            <span className="ml-2 text-[#7fd4ff]">箭頭</span> 代表漂移方向
          </span>
        )}
      </div>

      {cur != null && <SpeciesCard />}
      <StationTable />
      <SstChart />
    </>
  )
}
