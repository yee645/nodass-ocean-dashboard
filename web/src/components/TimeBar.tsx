import { useEffect } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { useFishingData, useForecastData } from '@/data/useData'

const leadShort = (d: number): string => (d === 0 ? '今日' : `+${d}天`)
const tfmt = (t: string): string => t.slice(5, 16).replace('T', ' ')

/** 底部時間列：未來=預報時段(leads)；現在=逐時回放(times)。皆支援拖曳 + 播放。 */
export default function TimeBar() {
  const timeMode = useAppStore((s) => s.timeMode)
  const leadIndex = useAppStore((s) => s.leadIndex)
  const setLeadIndex = useAppStore((s) => s.setLeadIndex)
  const nowTimeIndex = useAppStore((s) => s.nowTimeIndex)
  const setNowTimeIndex = useAppStore((s) => s.setNowTimeIndex)
  const playing = useAppStore((s) => s.playing)
  const setPlaying = useAppStore((s) => s.setPlaying)
  const { data: forecast } = useForecastData()
  const { data: fishing } = useFishingData()

  const leads = forecast?.meta.leads ?? []
  const times = fishing?.times ?? []
  const len = timeMode === 'future' ? leads.length : times.length

  // 自動播放：未來 1.1s、現在 0.9s（對應舊頁）。
  useEffect(() => {
    if (!playing || len <= 1) return
    const period = timeMode === 'future' ? 1100 : 900
    const t = setInterval(() => {
      const s = useAppStore.getState()
      if (timeMode === 'future') s.setLeadIndex((s.leadIndex + 1) % len)
      else
        s.setNowTimeIndex(
          (Math.min(len - 1, s.nowTimeIndex) + 1) % len,
        )
    }, period)
    return () => clearInterval(t)
  }, [playing, len, timeMode, setLeadIndex, setNowTimeIndex])

  if (timeMode === 'past' || len === 0) return null

  if (timeMode === 'future') {
    const li = Math.max(0, Math.min(leads.length - 1, leadIndex))
    const cur = leads[li]
    return (
      <Bar
        playing={playing}
        onPlay={() => setPlaying(!playing)}
        label={`${leadShort(cur.d)}（${cur.valid.slice(5, 16)}）`}
        value={li}
        max={leads.length - 1}
        onChange={setLeadIndex}
        ticks={leads.map((l) => leadShort(l.d))}
      />
    )
  }

  // now
  const ti = Math.max(0, Math.min(times.length - 1, nowTimeIndex))
  return (
    <Bar
      playing={playing}
      onPlay={() => setPlaying(!playing)}
      label={tfmt(times[ti])}
      value={ti}
      max={times.length - 1}
      onChange={setNowTimeIndex}
      ticks={[times[0].slice(5, 10), times[times.length - 1].slice(5, 10)]}
    />
  )
}

interface BarProps {
  playing: boolean
  onPlay: () => void
  label: string
  value: number
  max: number
  onChange: (i: number) => void
  ticks: string[]
}

function Bar({ playing, onPlay, label, value, max, onChange, ticks }: BarProps) {
  return (
    <div className="group absolute bottom-3 left-1/2 z-[600] flex max-w-[92vw] -translate-x-1/2 items-center gap-2 rounded-full border border-white/10 bg-panel/45 px-3 py-1.5 opacity-70 shadow-md backdrop-blur-sm transition hover:bg-panel/80 hover:opacity-100">
      <button
        onClick={onPlay}
        title="自動播放"
        className="type-caption flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-full text-[#cfe0f5] hover:bg-accent hover:text-white"
      >
        {playing ? '❙❙' : '▶'}
      </button>
      <div className="flex min-w-[min(320px,64vw)] flex-col gap-px">
        <div className="type-caption text-center font-medium text-muted transition-colors group-hover:text-ink-bright">
          {label}
        </div>
        <input
          type="range"
          min={0}
          max={max}
          step={1}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="slim-range m-0 w-full cursor-pointer accent-accent"
        />
        {/* 刻度預設隱藏，hover 才浮現，讓滑桿更低調 */}
        <div className="type-micro flex max-h-0 justify-between overflow-hidden text-muted opacity-0 transition-all group-hover:max-h-4 group-hover:opacity-100">
          {ticks.map((t, i) => (
            <span key={i}>{t}</span>
          ))}
        </div>
      </div>
    </div>
  )
}
