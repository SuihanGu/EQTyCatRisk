<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { CouplingEvent } from '../types'

const props = defineProps<{
  event: CouplingEvent | null | undefined
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

function buildOption(): echarts.EChartsOption {
  const event = props.event
  if (!event) {
    return {
      title: { text: 'No data', left: 'center', top: 'middle', textStyle: { color: '#94a3b8', fontSize: 14 } },
    }
  }

  const path = event.typhoonPath
  const winds =
    event.typhoonWinds?.length === path.length
      ? event.typhoonWinds
      : path.map((p, i) => p.windMs ?? event.windMs * (0.55 + (i / Math.max(path.length - 1, 1)) * 0.45))

  const step = Math.max(1, Math.ceil(path.length / 12))
  const labels = path.map((_, i) => (i % step === 0 || i === path.length - 1 ? `P${i + 1}` : ''))

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params
        if (!p || typeof p.dataIndex !== 'number') return ''
        const pt = path[p.dataIndex]
        const w = winds[p.dataIndex]
        if (!pt || w == null) return ''
        return `Point ${p.dataIndex + 1}<br/>Wind ${w.toFixed(1)} m/s<br/>Location ${pt.lat.toFixed(2)}°, ${pt.lng.toFixed(2)}°`
      },
    },
    grid: { left: 48, right: 24, top: 40, bottom: 36 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: 'm/s',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
      axisLabel: { color: '#64748b' },
    },
    series: [
      {
        name: 'Track wind',
        type: 'line',
        data: winds.map((w) => Number(w.toFixed(2))),
        smooth: true,
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(14, 165, 164, 0.35)' },
            { offset: 1, color: 'rgba(14, 165, 164, 0.02)' },
          ]),
        },
        lineStyle: { color: '#0ea5a4', width: 2.5 },
        itemStyle: { color: '#0f766e' },
        symbol: 'circle',
        symbolSize: path.length > 40 ? 3 : 6,
      },
    ],
    // title: {
    //   text: `峰值 ${peak.toFixed(1)} m/s · ${path.length} 点`,
    //   left: 12,
    //   top: 8,
    //   textStyle: { fontSize: 13, fontWeight: 600, color: '#1e293b' },
    // },
  }
}

function render() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  chart.setOption(buildOption(), true)
}

watch(() => props.event, render, { deep: true })

onMounted(() => {
  render()
  window.addEventListener('resize', onWindowResize)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

function onWindowResize() {
  chart?.resize()
}
</script>

<template>
  <section class="chart-panel">
    <div class="chart-panel-head">
      <h3>Typhoon wind</h3>
      <!-- <span class="chart-tag">完整路径风速</span> -->
    </div>
    <div ref="chartRef" class="chart-container" />
  </section>
</template>
