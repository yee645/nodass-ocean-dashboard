import { useAppStore } from '@/store/useAppStore'
import { useForecastData } from '@/data/useData'

/** 魚種複選晶片（baseField=habitat 時顯示）；驅動跨時段共享的 species。 */
export default function SpeciesChips() {
  const species = useAppStore((s) => s.species)
  const setSpecies = useAppStore((s) => s.setSpecies)
  const { data: forecast } = useForecastData()
  const all = forecast?.meta.species ?? []

  if (!all.length) return null
  const sel = new Set(species)
  const toggle = (nm: string) => {
    const next = new Set(sel)
    if (next.has(nm)) next.delete(nm)
    else next.add(nm)
    setSpecies([...next])
  }

  return (
    <div>
      <div className="mb-1 text-[0.78rem] font-semibold text-muted">
        魚種（可複選）
      </div>
      <div className="flex max-h-[150px] flex-wrap gap-1.5 overflow-auto rounded-lg border border-border bg-panel-2 p-1.5">
        {all.map((nm) => {
          const on = sel.has(nm)
          return (
            <label
              key={nm}
              onClick={(e) => {
                e.preventDefault()
                toggle(nm)
              }}
              className={
                'flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-[14px] border px-2.5 py-1 text-[0.82rem] ' +
                (on
                  ? 'border-ok bg-ok-bg text-ok-ink'
                  : 'border-border-strong bg-surface text-[#cdd9e5]')
              }
            >
              <input type="checkbox" readOnly checked={on} className="accent-ok" />
              {nm}
            </label>
          )
        })}
      </div>
      <div className="mt-1.5 flex gap-1.5">
        <button
          onClick={() => setSpecies([...all])}
          className="cursor-pointer rounded-lg border border-border-strong bg-surface px-2.5 py-1 text-[0.8rem] text-muted hover:text-ink"
        >
          全選
        </button>
        <button
          onClick={() => setSpecies([])}
          className="cursor-pointer rounded-lg border border-border-strong bg-surface px-2.5 py-1 text-[0.8rem] text-muted hover:text-ink"
        >
          清除
        </button>
      </div>
    </div>
  )
}
