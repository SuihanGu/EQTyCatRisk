<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

export interface LossItem {
  id: string
  name: string
  value: number
}

const props = withDefaults(
  defineProps<{
    items: LossItem[]
    title?: string
    subtitle?: string
    /** 图表最多展示的前 N 名（其余计入合计） */
    topN?: number
  }>(),
  {
    title: 'Loss distribution',
    subtitle: 'Relative loss index by region',
    topN: 20,
  },
)

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

const ranked = computed(() =>
  [...props.items].sort((a, b) => b.value - a.value),
)

const chartItems = computed(() => ranked.value.slice(0, props.topN))

const summary = computed(() => {
  const values = ranked.value.map((r) => r.value)
  const total = values.reduce((sum, v) => sum + v, 0)
  const top = ranked.value[0]
  const affected = values.filter((v) => v > 0).length
  return { total, top, affected }
})

function lossColor(value: number, max: number): string {
  const ratio = max > 0 ? value / max : 0
  if (ratio > 0.72) return '#dc2626'
  if (ratio > 0.45) return '#0d9488'
  if (ratio > 0.2) return '#14b8a6'
  return '#94a3b8'
}

function buildOption(): echarts.EChartsOption {
  const items = [...chartItems.value].reverse()
  const max = items.length ? Math.max(...items.map((i) => i.value), 1) : 1
  const names = items.map((i) => i.name)
  const values = items.map((i) => i.value)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params
        if (!p || typeof p.dataIndex !== 'number') return ''
        const item = items[p.dataIndex]
        if (!item) return ''
        const pct = summary.value.total > 0 ? ((item.value / summary.value.total) * 100).toFixed(1) : '0'
        return `${item.name}<br/>Loss index ${item.value.toLocaleString()}<br/>Share ${pct}%`
      },
    },
    grid: { left: 96, right: 48, top: 16, bottom: 24 },
    xAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#334155', fontSize: 11, fontWeight: 500 },
    },
    series: [
      {
        type: 'bar',
        data: values.map((v) => ({
          value: v,
          itemStyle: {
            color: lossColor(v, max),
            borderRadius: [0, 4, 4, 0],
          },
        })),
        barWidth: 12,
        label: {
          show: true,
          position: 'right',
          color: '#475569',
          fontSize: 10,
          fontFamily: 'ui-monospace, monospace',
          formatter: ({ value }) =>
            typeof value === 'number' ? value.toLocaleString() : '',
        },
      },
    ],
  }
}

function render() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  chart.setOption(buildOption(), true)
}

watch(() => props.items, render, { deep: true })

onMounted(() => {
  render()
  window.addEventListener('resize', () => chart?.resize())
})

onUnmounted(() => {
  chart?.dispose()
  chart = null
})
</script>

<template>
  <section class="loss-distribution">
    <div class="loss-distribution-head">
      <div>
        <h3>{{ title }}</h3>
        <p>{{ subtitle }}</p>
      </div>
      <div class="loss-legend">
        <span class="legend-item"><i class="dot low" />Low</span>
        <span class="legend-item"><i class="dot mid" />Mid</span>
        <span class="legend-item"><i class="dot high" />High</span>
      </div>
    </div>

    <div class="loss-summary">
      <div class="summary-cell">
        <span class="summary-label">Total index</span>
        <span class="summary-value">{{ summary.total.toLocaleString() }}</span>
      </div>
      <div class="summary-cell">
        <span class="summary-label">Top region</span>
        <span class="summary-value text">{{ summary.top?.name ?? '—' }}</span>
      </div>
      <div class="summary-cell">
        <span class="summary-label">Regions</span>
        <span class="summary-value">{{ summary.affected }}</span>
      </div>
    </div>

    <div ref="chartRef" class="loss-chart" />

    <div class="loss-rank-strip">
      <div
        v-for="(item, index) in ranked.slice(0, 5)"
        :key="item.id"
        class="rank-chip"
        :class="{ lead: index === 0 }"
      >
        <span class="rank-no">{{ index + 1 }}</span>
        <span class="rank-name">{{ item.name }}</span>
        <span class="rank-val">{{ item.value.toLocaleString() }}</span>
      </div>
    </div>
  </section>
</template>
