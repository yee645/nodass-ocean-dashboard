import { gradientCss } from '@/map/palettes'
import { useLegendKpi } from '@/map/useLegendKpi'

/** 圖例（漸層條 + 低→高 + 備註）與 KPI 統計，對應舊 setLegend/setKpi。 */
export default function Legend() {
  const { available, fieldLabel, palette, lohiNote, kpi } = useLegendKpi()
  if (!available) return null

  return (
    <div className="flex flex-col gap-2">
      {kpi.length > 0 && (
        <div className="flex flex-wrap gap-2.5">
          {kpi.map(([k, v]) => (
            <div
              key={k}
              className="flex-auto rounded-md bg-surface px-3 py-2 text-center text-[0.82rem]"
            >
              {k}
              <b className="block text-[clamp(1rem,1.8vw,1.2rem)]">{v}</b>
            </div>
          ))}
        </div>
      )}
      <div className="text-[0.78rem] text-muted">
        {fieldLabel}
        <div
          className="mt-1 h-3 w-[170px] rounded-[3px]"
          style={{ background: gradientCss(palette) }}
        />
        低 → 高
        {lohiNote && <span className="ml-2 text-muted-2">{lohiNote}</span>}
      </div>
    </div>
  )
}
