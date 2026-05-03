<template>
  <div class="wrap">
    <header>
      <h1>Monitoring the Attic Temperature </h1>
      <span v-if="sensorStale" class="offline-badge">Sensor offline</span>
      <div class="unit-toggle" role="group" aria-label="Temperature unit">
        <button type="button" :class="{ active: unit === 'F' }" @click="unit = 'F'">°F</button>
        <button type="button" :class="{ active: unit === 'C' }" @click="unit = 'C'">°C</button>
      </div>
    </header>

    <div v-if="loading" class="status">Loading…</div>
    <div v-else-if="error" class="status error">{{ error }}</div>
    <template v-else>
      <div v-if="current" class="current">
        <div class="current-col">
          <span class="current-temp attic">{{ current.attic }}</span>
          <span class="current-label">Attic</span>
        </div>
        <div class="current-col delta-col">
          <span class="current-delta" :class="{ danger: current.danger }">{{ current.deltaStr }}</span>
          <span class="current-label">vs outdoors</span>
        </div>
        <div class="current-col">
          <span class="current-temp outdoor">{{ current.outdoor }}</span>
          <span class="current-label">Outdoor</span>
        </div>
      </div>

      <Line :data="chartData" :options="chartOptions" />
      <div class="camera-wrap">
        <iframe
          src="https://vauth.command.verkada.com/__v/bens-spyware/embed/html/f2db838e-fd72-4a89-9cd8-9a496bba0ace/"
          frameborder="0"
          allowfullscreen
        ></iframe>
      </div>
      <p class="footer">Updated {{ cachedAt }}</p>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Title,
  Tooltip,
  Legend,
  TimeScale,
} from 'chart.js'
import 'chartjs-adapter-date-fns'

ChartJS.register(LinearScale, PointElement, LineElement, Filler, Title, Tooltip, Legend, TimeScale)

const API_URL = import.meta.env.VITE_API_URL || ''

const loading = ref(true)
const error = ref(null)
const rawData = ref(null)
const unit = ref('F')

const COLORS = ['#f97316', '#38bdf8']

const toF = c => c * 9 / 5 + 32
const toDisplay = c => unit.value === 'F' ? +(toF(c)).toFixed(1) : +c.toFixed(1)
const fmt = v => `${v}°`

// Linear interpolation of outdoor °C at an arbitrary sensor timestamp.
// Outdoor data is hourly; this maps it onto every sensor point so mode:'index'
// always resolves exactly one point per dataset.
function interpOutdoor(targetTime, outdoorPoints) {
  if (!outdoorPoints.length) return null
  const t = new Date(targetTime).getTime()
  const first = new Date(outdoorPoints[0].x).getTime()
  const last  = new Date(outdoorPoints[outdoorPoints.length - 1].x).getTime()
  if (t <= first) return outdoorPoints[0].y
  if (t >= last)  return outdoorPoints[outdoorPoints.length - 1].y
  let lo = 0, hi = outdoorPoints.length - 1
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1
    new Date(outdoorPoints[mid].x).getTime() <= t ? (lo = mid) : (hi = mid)
  }
  const t0 = new Date(outdoorPoints[lo].x).getTime()
  const t1 = new Date(outdoorPoints[hi].x).getTime()
  const frac = t0 === t1 ? 0 : (t - t0) / (t1 - t0)
  return outdoorPoints[lo].y + frac * (outdoorPoints[hi].y - outdoorPoints[lo].y)
}

// Thresholds in raw °C: 30 °F delta ≈ 16.67 °C, 130 °F ≈ 54.44 °C
const isDanger = computed(() => {
  const [sensor, outdoor] = rawData.value?.datasets ?? []
  if (!sensor?.data?.length || !outdoor?.data?.length) return false
  const lastSensor  = sensor.data[sensor.data.length - 1].y
  const lastOutdoor = outdoor.data[outdoor.data.length - 1].y
  return (lastSensor - lastOutdoor) >= 16.67 || lastSensor >= 54.44
})

const current = computed(() => {
  if (!rawData.value) return null
  const [sensor, outdoor] = rawData.value.datasets
  if (!sensor?.data?.length || !outdoor?.data?.length) return null
  const a = toDisplay(sensor.data[sensor.data.length - 1].y)
  const o = toDisplay(outdoor.data[outdoor.data.length - 1].y)
  const d = +(a - o).toFixed(1)
  return {
    attic: fmt(a),
    outdoor: fmt(o),
    deltaStr: `${d > 0 ? '+' : ''}${d}°`,
    danger: isDanger.value,
  }
})

const chartData = computed(() => {
  if (!rawData.value) return { datasets: [] }
  const [sensorDs, outdoorDs] = rawData.value.datasets

  const sensorData  = sensorDs.data.map(p => ({ x: p.x, y: toDisplay(p.y) }))
  // Build outdoor aligned to every sensor timestamp via interpolation
  const outdoorData = sensorDs.data.map(p => ({
    x: p.x,
    y: toDisplay(interpOutdoor(p.x, outdoorDs.data)),
  }))

  return {
    datasets: [
      {
        label: 'Sensor Temperature',
        data: sensorData,
        borderColor: COLORS[0],
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        pointRadius: 2,
        pointHoverRadius: 4,
        tension: 0.3,
        fill: { target: 1, above: 'rgba(249,115,22,0.15)', below: 'rgba(56,189,248,0.15)' },
      },
      {
        label: 'Outdoor Temperature',
        data: outdoorData,
        borderColor: COLORS[1],
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        pointRadius: 2,
        pointHoverRadius: 4,
        tension: 0.3,
        fill: false,
      },
    ],
  }
})

const cachedAt = computed(() => {
  if (!rawData.value) return ''
  return new Date(rawData.value.cached_at).toLocaleString()
})

const sensorStale = computed(() => {
  const ds = rawData.value?.datasets?.[0]
  if (!ds?.data?.length) return false
  const last = new Date(ds.data[ds.data.length - 1].x)
  return Date.now() - last > 60 * 60 * 1000
})

const fmtTime = ms => {
  const d = new Date(ms)
  const h = d.getHours(), m = d.getMinutes()
  return `${h % 12 || 12}${m ? `:${String(m).padStart(2, '0')}` : ''}${h >= 12 ? 'pm' : 'am'}`
}

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: true,
  aspectRatio: 2.4,
  interaction: { intersect: false, mode: 'index' },
  scales: {
    x: {
      type: 'time',
      time: { unit: 'hour' },
      border: { display: false },
      grid: { display: false },
      ticks: {
        color: '#6b7280',
        font: { size: 11 },
        maxRotation: 0,
        maxTicksLimit: 12,
        callback: val => {
          const d = new Date(val)
          const h = d.getHours()
          if (h === 0) return d.toLocaleDateString('en', { month: 'short', day: 'numeric' })
          return `${h % 12 || 12}${h >= 12 ? 'pm' : 'am'}`
        },
      },
    },
    y: {
      border: { display: false },
      grid: { color: 'rgba(255,255,255,0.05)', drawTicks: false },
      ticks: { color: '#6b7280', font: { size: 11 }, padding: 8 },
    },
  },
  plugins: {
    legend: {
      position: 'top',
      align: 'end',
      labels: { color: '#9ca3af', boxWidth: 24, boxHeight: 2, padding: 20, font: { size: 11 } },
    },
    tooltip: {
      callbacks: {
        title: items => items.length ? fmtTime(items[0].parsed.x) : '',
        label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}°${unit.value}`,
        afterBody: items => {
          const a = items.find(i => i.datasetIndex === 0)?.parsed.y
          const o = items.find(i => i.datasetIndex === 1)?.parsed.y
          if (a == null || o == null) return []
          const d = a - o
          return [`Δ ${d >= 0 ? '+' : ''}${d.toFixed(1)}°${unit.value} hotter`]
        },
      },
    },
  },
}))

onMounted(async () => {
  try {
    const res = await fetch(`${API_URL}/data`)
    if (!res.ok) throw new Error(`Server returned ${res.status}`)
    rawData.value = await res.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  background: #0f0f0f;
  color: #e2e2e2;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  min-height: 100vh;
}

.wrap {
  max-width: 1000px;
  margin: 0 auto;
  padding: 3rem 1.5rem;
}

header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

h1 {
  font-size: 0.8rem;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6b7280;
}

.offline-badge {
  font-size: 0.65rem;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  padding: 0.2rem 0.5rem;
  border-radius: 9999px;
}

.unit-toggle {
  margin-left: auto;
  display: inline-flex;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 9999px;
  padding: 2px;
}

.unit-toggle button {
  background: transparent;
  border: 0;
  color: #6b7280;
  font: inherit;
  font-size: 0.7rem;
  font-weight: 500;
  letter-spacing: 0.04em;
  padding: 0.25rem 0.7rem;
  border-radius: 9999px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.unit-toggle button.active {
  background: rgba(255, 255, 255, 0.08);
  color: #e2e2e2;
}

.current {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 2rem;
  padding: 1.25rem 1.5rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
}

.current-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  flex: 1;
}

.delta-col {
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
}

.current-temp {
  font-size: 2rem;
  font-weight: 300;
  letter-spacing: -0.02em;
  line-height: 1;
}

.current-temp.attic   { color: #f97316; }
.current-temp.outdoor { color: #38bdf8; }

.current-delta {
  font-size: 1.5rem;
  font-weight: 300;
  letter-spacing: -0.02em;
  line-height: 1;
  color: #9ca3af;
  transition: color 0.3s;
}

.current-delta.danger { color: #ef4444; }

.current-label {
  font-size: 0.65rem;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #4b5563;
}

.status {
  padding: 4rem 0;
  text-align: center;
  color: #4b5563;
  font-size: 0.875rem;
}

.status.error { color: #ef4444; }

.camera-wrap {
  margin-top: 2rem;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.06);
  aspect-ratio: 4 / 3;
}

.camera-wrap iframe {
  width: 100%;
  height: 100%;
  display: block;
}

.footer {
  margin-top: 0.75rem;
  font-size: 0.7rem;
  color: #374151;
  text-align: right;
}
</style>
