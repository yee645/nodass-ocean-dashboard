import { useAppStore } from '@/store/useAppStore'
import { useFishingData } from '@/data/useData'
import { colorFor } from '@/map/layers/nowMath'

const rgb = (c: [number, number, number]): string => `rgb(${c[0]},${c[1]},${c[2]})`

export default function StationTable() {
  const species = useAppStore((s) => s.species)
  const selId = useAppStore((s) => s.selectedStationId)
  const setSelected = useAppStore((s) => s.setSelectedStation)
  const { data: fishing } = useFishingData()
  if (!fishing) return null

  const cur = species.length ? species[0] : null
  const isSp = cur != null
  const valOf = (s: (typeof fishing.stations)[number]): number =>
    cur == null ? s.fish_score : (s.species[cur] ?? 0)
  const rows = [...fishing.stations].sort((a, b) => valOf(b) - valOf(a))

  return (
    <div className="border-t border-border pt-2">
      <h3 className="mb-1.5 text-[clamp(0.9rem,1.4vw,1rem)]">
        {isSp ? `${cur} 適合度排序` : '潛在漁場排序'}（點列看海溫時序）
      </h3>
      <div className="table-scroll max-h-[210px] overflow-auto rounded-md border border-border bg-panel-2/40">
        <table className="w-full table-fixed border-collapse text-[0.78rem]">
          <thead>
            <tr className="sticky top-0 z-10 bg-panel-2 text-muted">
              <th className="w-[31%] border-b border-border px-2 py-1.5 text-left font-semibold">站名</th>
              <th className="w-[18%] border-b border-border px-2 py-1.5 text-left font-semibold">緯經度</th>
              <th className="w-[11%] border-b border-border px-2 py-1.5 text-left font-semibold">SST</th>
              {isSp ? (
                <th className="w-[40%] border-b border-border px-2 py-1.5 text-left font-semibold">適合度</th>
              ) : (
                <>
                  <th className="w-[12%] border-b border-border px-2 py-1.5 text-left font-semibold">鋒面</th>
                  <th className="w-[12%] border-b border-border px-2 py-1.5 text-left font-semibold">流速</th>
                  <th className="w-[16%] border-b border-border px-2 py-1.5 text-left font-semibold">指標</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const v = valOf(s)
              const on = s.id === selId
              return (
                <tr
                  key={s.id}
                  onClick={() => setSelected(s.id)}
                  className={
                    'cursor-pointer ' + (on ? 'bg-surface' : 'hover:bg-surface')
                  }
                >
                  <td className="truncate border-b border-border px-2 py-1.5" title={s.name}>
                    {s.name}
                  </td>
                  <td className="border-b border-border px-2 py-1.5 text-[0.72rem] text-[#cbd8ea]">
                    {s.lat.toFixed(2)},{s.lon.toFixed(2)}
                  </td>
                  <td className="border-b border-border px-2 py-1.5">{s.sst}</td>
                  {isSp ? (
                    <td className="border-b border-border px-2 py-1.5">
                      <span
                        className="inline-flex max-w-full rounded-[10px] px-2 py-0.5 text-white"
                        style={{ background: rgb(colorFor(v)) }}
                      >
                        {v}
                      </span>
                    </td>
                  ) : (
                    <>
                      <td className="border-b border-border px-2 py-1.5">{s.front}</td>
                      <td className="border-b border-border px-2 py-1.5">{s.current ?? '-'}</td>
                      <td className="border-b border-border px-2 py-1.5">
                        <span
                          className="inline-flex max-w-full rounded-[10px] px-2 py-0.5 text-white"
                          style={{ background: rgb(colorFor(v)) }}
                        >
                          {v} {s.level}
                        </span>
                      </td>
                    </>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
