import { useAppStore, type BaseField, type Overlays } from '@/store/useAppStore'
import SpeciesChips from './SpeciesChips'
import Legend from './Legend'

/** 互斥底層純量場清單（對應舊 forecast 的 BASE）。 */
const BASE_FIELDS: { key: BaseField; label: string }[] = [
  { key: 'sst', label: '海溫 SST (°C)' },
  { key: 'cspd', label: '海流速 (m/s)' },
  { key: 'ws', label: '風速 (m/s，模式場)' },
  { key: 'wl', label: '潮位 (m)' },
  { key: 'conf', label: '資料信心(出現點支持)' },
  { key: 'chl', label: '葉綠素氣候平均 (mg/m³)' },
  { key: 'habitat', label: '棲地適合度(選魚種)' },
]

/** 可混用 overlay 清單。 */
const OVERLAYS: { key: keyof Overlays; label: string }[] = [
  { key: 'current', label: '海流向量' },
  { key: 'wind', label: '風向量' },
]

/** 未來時段控制：基礎圖層(互斥) + overlay(可混用) + 低信心淡化 + 魚種 + 圖例。 */
export default function FuturePanel() {
  const baseField = useAppStore((s) => s.baseField)
  const setBaseField = useAppStore((s) => s.setBaseField)
  const overlays = useAppStore((s) => s.overlays)
  const toggleOverlay = useAppStore((s) => s.toggleOverlay)
  const confDim = useAppStore((s) => s.confDim)
  const setConfDim = useAppStore((s) => s.setConfDim)

  return (
    <>
      <div>
        <div className="type-section-title mb-1 text-muted">
          基礎圖層（互斥）
        </div>
        <div className="flex flex-col gap-1">
          {BASE_FIELDS.map((f) => {
            const on = f.key === baseField
            return (
              <button
                key={f.key}
                onClick={() => setBaseField(f.key)}
                className={
                  'type-control cursor-pointer rounded-lg border px-3 py-1.5 text-left ' +
                  (on
                    ? 'border-accent bg-accent font-semibold text-white'
                    : 'border-border-strong bg-surface text-muted hover:text-ink')
                }
              >
                {f.label}
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <div className="type-section-title mb-1 text-muted">
          疊加圖層（可混用）
        </div>
        <div className="flex flex-wrap gap-x-3.5 gap-y-2">
          {OVERLAYS.map((o) => (
            <label
              key={o.key}
              className="type-control flex cursor-pointer items-center gap-1 text-ink"
            >
              <input
                type="checkbox"
                checked={overlays[o.key]}
                onChange={() => toggleOverlay(o.key)}
                className="scale-[1.15]"
              />
              {o.label}
            </label>
          ))}
          <label
            className="type-control flex cursor-pointer items-center gap-1 text-ink"
            title="信心 < 0.3 的格子(遠離出現點、模型外推)降透明度標示"
          >
            <input
              type="checkbox"
              checked={confDim}
              onChange={(e) => setConfDim(e.target.checked)}
              className="scale-[1.15]"
            />
            低信心淡化
          </label>
        </div>
      </div>

      {baseField === 'habitat' && <SpeciesChips />}

      <Legend />
    </>
  )
}
