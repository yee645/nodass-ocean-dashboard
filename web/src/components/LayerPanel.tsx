import { useAppStore } from '@/store/useAppStore'
import FuturePanel from './FuturePanel'
import NowPanel from './NowPanel'
import PastPanel from './PastPanel'

const TITLE: Record<string, string> = {
  future: '預報圖層',
  now: '魚種圖層',
  past: '歷史圖層',
}

export default function LayerPanel() {
  const timeMode = useAppStore((s) => s.timeMode)
  const toggle = useAppStore((s) => s.toggleLayerPanel)

  return (
    <aside className="absolute inset-y-0 right-0 z-[600] flex w-[88vw] max-w-[360px] flex-col border-l border-border-strong bg-panel shadow-[0_8px_26px_rgba(0,0,0,.45)] md:static md:z-auto md:w-[30%] md:min-w-[300px] md:max-w-[460px] md:shadow-none">
      <header className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-[10px]">
        <h2 className="flex-1 text-[0.95rem] text-ink-bright">
          {TITLE[timeMode]}
        </h2>
        <button
          onClick={toggle}
          title="收合圖層"
          aria-label="收合圖層"
          className="flex h-7 w-7 items-center justify-center rounded-md border border-border-strong bg-surface text-muted hover:border-accent hover:text-white"
        >
          &times;
        </button>
      </header>

      <div className="panel-scroll flex flex-1 flex-col gap-2.5 overflow-auto px-3 py-2.5">
        {timeMode === 'future' && <FuturePanel />}
        {timeMode === 'now' && <NowPanel />}
        {timeMode === 'past' && <PastPanel />}
      </div>
    </aside>
  )
}
