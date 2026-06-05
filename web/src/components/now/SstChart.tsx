import './chartSetup'
import { Line } from 'react-chartjs-2'
import type { ChartOptions } from 'chart.js'
import { useAppStore } from '@/store/useAppStore'
import { useFishingData } from '@/data/useData'

const OPTIONS: ChartOptions<'line'> = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { labels: { color: '#cdd9e5' } } },
  scales: {
    x: { ticks: { color: '#8aa0b8', maxTicksLimit: 8 }, grid: { color: '#1c2c46' } },
    y: {
      title: { display: true, text: 'SST (°C)', color: '#ff7043' },
      ticks: { color: '#8aa0b8' },
      grid: { color: '#1c2c46' },
    },
  },
}

export default function SstChart() {
  const selId = useAppStore((s) => s.selectedStationId)
  const species = useAppStore((s) => s.species)
  const { data: fishing } = useFishingData()
  if (!fishing) return null

  const cur = species.length ? species[0] : null
  const valOf = (s: (typeof fishing.stations)[number]): number =>
    cur == null ? s.fish_score : (s.species[cur] ?? 0)
  const sorted = [...fishing.stations].sort((a, b) => valOf(b) - valOf(a))
  const st = fishing.stations.find((s) => s.id === selId) ?? sorted[0]
  if (!st) return null

  const labels = st.sst_series.map((p) => p.t.slice(5, 16).replace('T', ' '))
  const values = st.sst_series.map((p) => p.v)

  return (
    <div className="border-t border-border pt-2">
      <h3 className="mb-1.5 text-[clamp(0.9rem,1.4vw,1rem)]">
        {st.name} - SST 時序（近 2 天）
      </h3>
      <div className="relative h-40 w-full">
        <Line
          options={OPTIONS}
          data={{
            labels,
            datasets: [
              {
                label: 'Sea Temperature (°C)',
                data: values,
                borderColor: '#ff7043',
                backgroundColor: 'rgba(255,112,67,.15)',
                fill: true,
                tension: 0.3,
                borderWidth: 2,
                pointRadius: 3.5,
                pointHoverRadius: 6,
                pointBackgroundColor: '#ff7043',
              },
            ],
          }}
        />
      </div>
    </div>
  )
}
