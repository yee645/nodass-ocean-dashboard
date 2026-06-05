import { useAppStore, type BaseField } from '@/store/useAppStore'
import { useHiresData } from '@/data/useData'
import { gradientCss, type PaletteName } from '@/map/palettes'
import { resolveHiresKeys } from '@/map/layers/hiresMath'
import { LOWCONF } from '@/map/layers/fieldConfig'

const BASE: { key: BaseField; label: string; pal: PaletteName }[] = [
  { key: 'sst', label: '海表溫度 SST (°C)', pal: 'jet' },
  { key: 'chl', label: '葉綠素 a (mg/m³)', pal: 'jet' },
  { key: 'front', label: '海溫鋒面強度', pal: 'jet' },
  { key: 'conf', label: '資料信心度', pal: 'conf' },
  { key: 'habitat', label: '魚種棲地適合度', pal: 'jet' },
]

export default function PastPanel() {
  const baseField = useAppStore((s) => s.baseField)
  const setBaseField = useAppStore((s) => s.setBaseField)
  const confDim = useAppStore((s) => s.confDim)
  const setConfDim = useAppStore((s) => s.setConfDim)
  const species = useAppStore((s) => s.species)
  const setSpecies = useAppStore((s) => s.setSpecies)
  const { data: hires } = useHiresData()

  if (!hires) return <div className="text-[0.8rem] text-muted">資料載入中...</div>

  const { meta, layers } = hires
  const hasConf = meta.has_conf
  const bases = BASE.filter((b) => b.key !== 'conf' || hasConf)
  const cfg = bases.find((b) => b.key === baseField) ?? bases[0]
  const activeField = cfg.key

  const names = [...new Set([...meta.thermal, ...meta.sdm.map((x) => x.name)])]
  const sdmMap = new Map(meta.sdm.map((x) => [x.name, x.auc]))
  const selected = new Set(species)
  const habitatKeys = resolveHiresKeys(layers, species)
  const arr: (number | null)[] =
    activeField === 'habitat'
      ? layers.sst.map((_, i) => {
          let best: number | null = null
          for (const key of habitatKeys) {
            const v = layers[key]?.[i]
            if (v != null && (best == null || v > best)) best = v
          }
          return best
        })
      : (layers[activeField] ?? [])

  let n = 0
  let sum = 0
  let max = -Infinity
  let low = 0
  for (const v of arr) {
    if (v == null) continue
    n++
    sum += v
    if (v > max) max = v
    if (v < LOWCONF) low++
  }
  const avg = n ? sum / n : 0
  const kpi: [string, string][] =
    activeField === 'conf'
      ? [
          ['有效格點', String(n)],
          ['平均信心', avg.toFixed(2)],
          ['低信心格點', String(low)],
          ['門檻', `<${LOWCONF}`],
        ]
      : activeField === 'habitat'
        ? [
            ['有效格點', String(n)],
            ['選取魚種', String(habitatKeys.length)],
            ['平均分', n ? avg.toFixed(0) : '--'],
            ['最高分', n ? String(Math.round(max)) : '--'],
          ]
        : [
            ['有效格點', String(n)],
            ['網格解析', '~4km'],
            ['平均', avg.toFixed(2)],
            ['最高', n ? max.toFixed(2) : '--'],
          ]

  const labelOf = (name: string): string => {
    const auc = sdmMap.get(name)
    return auc != null ? `${name} (SDM AUC ${auc})` : `${name} (適溫模型)`
  }

  const toggle = (name: string) => {
    const next = new Set(selected)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    setSpecies([...next])
  }

  return (
    <>
      <div>
        <div className="mb-1 text-[0.78rem] font-semibold text-muted">
          底圖圖層（單選）
        </div>
        <div className="flex flex-col gap-1">
          {bases.map((base) => {
            const on = base.key === activeField
            return (
              <button
                key={base.key}
                onClick={() => setBaseField(base.key)}
                className={
                  'cursor-pointer rounded-lg border px-3 py-1.5 text-left text-[0.85rem] ' +
                  (on
                    ? 'border-accent bg-accent font-semibold text-white'
                    : 'border-border-strong bg-surface text-muted hover:text-ink')
                }
              >
                {base.label}
              </button>
            )
          })}
        </div>
      </div>

      {hasConf && (
        <label
          className="flex cursor-pointer items-center gap-1 text-[0.82rem] text-ink"
          title={`信心度 < ${LOWCONF} 的格點會降低顯示亮度`}
        >
          <input
            type="checkbox"
            checked={confDim}
            onChange={(e) => setConfDim(e.target.checked)}
            className="scale-[1.15]"
          />
          低信心格點淡化
        </label>
      )}

      {activeField === 'habitat' && (
        <div>
          <div className="mb-1 text-[0.78rem] font-semibold text-muted">
            魚種（可複選）
          </div>
          <div className="chip-scroll flex max-h-[150px] flex-wrap gap-1.5 overflow-auto rounded-lg border border-border bg-panel-2 p-1.5">
            {names.map((name) => {
              const on = selected.has(name)
              return (
                <label
                  key={name}
                  onClick={(e) => {
                    e.preventDefault()
                    toggle(name)
                  }}
                  className={
                    'flex cursor-pointer items-center gap-1.5 rounded-[14px] border px-2.5 py-1 text-[0.82rem] ' +
                    (on
                      ? 'border-ok bg-ok-bg text-ok-ink'
                      : 'border-border-strong bg-surface text-[#cdd9e5]')
                  }
                >
                  <input type="checkbox" readOnly checked={on} className="accent-ok" />
                  {labelOf(name)}
                </label>
              )
            })}
          </div>
          <div className="mt-1.5 flex gap-1.5">
            <button
              onClick={() => setSpecies([...names])}
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
      )}

      <div className="flex flex-wrap gap-2.5">
        {kpi.map(([key, value]) => (
          <div
            key={key}
            className="flex-auto rounded-md bg-surface px-3 py-2 text-center text-[0.82rem]"
          >
            {key}
            <b className="block text-[clamp(1rem,1.8vw,1.2rem)]">{value}</b>
          </div>
        ))}
      </div>
      <div className="text-[0.78rem] text-muted">
        {activeField === 'habitat'
          ? habitatKeys.length > 1
            ? '多魚種以每個格點最高適合度顯示'
            : '魚種棲地適合度'
          : cfg.label}
        <div
          className="mt-1 h-3 w-[170px] rounded-[3px]"
          style={{ background: gradientCss(cfg.pal) }}
        />
        低 - 高
      </div>
    </>
  )
}
