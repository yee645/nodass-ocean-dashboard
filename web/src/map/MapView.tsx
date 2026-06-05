import { useEffect, useRef } from 'react'
import { Map as MaplibreMap, NavigationControl, Popup } from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import 'maplibre-gl/dist/maplibre-gl.css'
import './mapPopup.css'
import { basemapStyle } from './basemapStyle'
import { useDeckLayers } from './useDeckLayers'
import { orderLayers } from './layerOrder'

const TW_CENTER: [number, number] = [121.0, 23.7]

interface Props {
  resolvePopup?: (lng: number, lat: number) => string | null
}

export default function MapView({ resolvePopup }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MaplibreMap | null>(null)
  const overlayRef = useRef<MapboxOverlay | null>(null)
  const resolveRef = useRef(resolvePopup)
  const layers = useDeckLayers()

  useEffect(() => {
    resolveRef.current = resolvePopup
  }, [resolvePopup])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new MaplibreMap({
      container: containerRef.current,
      style: basemapStyle,
      center: TW_CENTER,
      zoom: 7,
      attributionControl: { compact: true },
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')

    const resizeObserver = new ResizeObserver(() => map.resize())
    resizeObserver.observe(containerRef.current)

    const overlay = new MapboxOverlay({
      interleaved: false,
      layers: [],
      getTooltip: (info) => {
        const station = info.object as
          | {
              name: string
              lat: number
              lon: number
              sst: number
              current: number | null
              fish_score: number
            }
          | undefined
        if (!station || typeof station.fish_score === 'undefined') return null
        return {
          html: `<b>${station.name}</b><br/>位置 ${station.lat.toFixed(3)}, ${station.lon.toFixed(3)}<br/>SST ${station.sst}°C / 流速 ${station.current ?? '-'}<br/>潛在漁場指標 ${station.fish_score}`,
          style: {
            background: '#15233b',
            color: '#e8eef7',
            border: '1px solid #2f456b',
            borderRadius: '6px',
            fontSize: '12px',
            padding: '6px 8px',
          },
        }
      },
    })
    map.addControl(overlay)

    map.on('click', (event) => {
      const fn = resolveRef.current
      if (!fn) return
      const html = fn(event.lngLat.lng, event.lngLat.lat)
      if (!html) return
      new Popup({
        className: 'nodass-map-popup',
        closeButton: true,
        maxWidth: '340px',
      })
        .setLngLat(event.lngLat)
        .setHTML(html)
        .addTo(map)
    })

    mapRef.current = map
    overlayRef.current = overlay
    return () => {
      resizeObserver.disconnect()
      overlayRef.current = null
      mapRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    overlayRef.current?.setProps({ layers: orderLayers(layers) })
  }, [layers])

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" />
    </div>
  )
}
