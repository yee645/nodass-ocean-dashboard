import { lazy, Suspense } from 'react'
import { useAppStore } from '@/store/useAppStore'
import LeftPanel from '@/components/LeftPanel'
import LayerPanel from '@/components/LayerPanel'
import TimeBar from '@/components/TimeBar'
import { usePopup } from '@/map/usePopup'

// 地圖模組(MapLibre + deck.gl)較重，lazy-load 以縮小首屏 bundle。
const MapView = lazy(() => import('@/map/MapView'))

/**
 * 應用外殼：地圖區(約 70%) + 可收納側欄(約 30%)。
 * 寬螢幕側欄佔版面 30%；窄螢幕側欄改為覆蓋地圖的抽屜(RWD)。
 */
export default function App() {
  const resolvePopup = usePopup()
  const collapsed = useAppStore((s) => s.layerPanelCollapsed)
  const toggle = useAppStore((s) => s.toggleLayerPanel)

  return (
    <div className="flex h-full">
      {/* 地圖區 */}
      <div className="relative min-w-0 flex-1">
        <Suspense
          fallback={
            <div className="type-caption absolute inset-0 flex items-center justify-center bg-mapbg text-muted">
              地圖載入中…
            </div>
          }
        >
          <MapView resolvePopup={resolvePopup} />
        </Suspense>

        <LeftPanel />
        <TimeBar />

        <div className="type-caption pointer-events-none absolute bottom-3 left-3 z-[550] max-w-[min(420px,52vw)] rounded-[10px] border border-border-strong bg-panel/80 px-3 py-2 text-[#c2d2e6] backdrop-blur-sm max-md:hidden">
          出航前參考：海象與環境為決策參考，正式以
          <b className="text-gold">中央氣象署官方海象/漁業氣象與海巡署警報</b>
          為準。
        </div>

        {/* 側欄收合時的重開鈕 */}
        {collapsed && (
          <button
            onClick={toggle}
            title="開啟圖層側欄"
            className="type-control absolute right-3 top-3 z-[600] flex items-center gap-1.5 rounded-lg border border-border-strong bg-panel/95 px-3 py-2 text-[#cfe0f5] shadow-[0_8px_26px_rgba(0,0,0,.45)] hover:border-accent hover:bg-accent hover:text-white"
          >
            <span className="type-icon-md">&#9776;</span> 圖層
          </button>
        )}
      </div>

      {/* 側欄（收合時不渲染，地圖區自動填滿） */}
      {!collapsed && <LayerPanel />}
    </div>
  )
}
