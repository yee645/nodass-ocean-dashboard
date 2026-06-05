import { useAppStore } from '@/store/useAppStore'
import { MODES } from '@/modes/modeConfig'

/** 左上浮動標題面板：標題 + 時段切換（對應舊 platform.html 左側面板）。 */
export default function LeftPanel() {
  const timeMode = useAppStore((s) => s.timeMode)
  const setTimeMode = useAppStore((s) => s.setTimeMode)
  const open = useAppStore((s) => s.leftPanelOpen)
  const setOpen = useAppStore((s) => s.setLeftPanelOpen)

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="開啟資訊"
        className="absolute left-3 top-3 z-[601] flex h-10 w-10 items-center justify-center rounded-[9px] border border-border-strong bg-panel/95 text-xl text-[#cfe0f5] shadow-[0_8px_26px_rgba(0,0,0,.45)] hover:border-accent hover:bg-accent hover:text-white"
      >
        &#9776;
      </button>
    )
  }

  return (
    <div className="absolute left-3 top-3 z-[600] max-h-[calc(100%-92px)] w-[min(310px,82vw)] overflow-auto rounded-[10px] border border-border-strong bg-panel/95 pb-2 shadow-[0_8px_26px_rgba(0,0,0,.45)]">
      <div className="flex items-start gap-2 px-3 pb-1 pt-[10px]">
        <div className="flex-1 text-[0.92rem] font-bold leading-[1.35] text-ink-bright">
          NODASS 漁場棲地平台（過去 · 現在 · 未來）
        </div>
        <button
          onClick={() => setOpen(false)}
          title="收合"
          className="shrink-0 cursor-pointer border-none bg-transparent text-[1.35rem] leading-none text-muted hover:text-white"
        >
          &times;
        </button>
      </div>
      <div className="px-3 pb-1.5 text-[0.72rem] leading-[1.5] text-muted">
        出航前參考：在過去/現在/未來之間切換，綜覽海象、環境與多魚種棲地潛勢
      </div>

      <div className="px-3 pb-0 pt-2 text-[0.78rem] font-semibold text-muted">
        時段
      </div>
      <div className="flex flex-col gap-1.5 px-3 pt-1">
        {MODES.map((m) => {
          const on = m.key === timeMode
          return (
            <button
              key={m.key}
              onClick={() => setTimeMode(m.key)}
              className={
                'cursor-pointer rounded-lg border px-3 py-2 text-left text-[0.85rem] ' +
                (on
                  ? 'border-accent bg-accent font-semibold text-white'
                  : 'border-border-strong bg-surface text-[#cdd9e5] hover:text-white')
              }
            >
              {m.label}
            </button>
          )
        })}
      </div>
      <div className="px-3 pt-1.5 text-[0.76rem] leading-[1.5] text-muted">
        {MODES.find((m) => m.key === timeMode)?.hint}
      </div>
    </div>
  )
}
