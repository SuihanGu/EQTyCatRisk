<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useEventStore } from '../stores/eventStore'
import RiskHeader from '../components/RiskHeader.vue'
import JapanMap from '../components/JapanMap.vue'
import LossResultCharts from '../components/LossResultCharts.vue'
import type { GridHeatMetric } from '../utils/gridLossLayer'
import { downloadLossCsv } from '../utils/csvDownloads'

const store = useEventStore()

const riskEvent = computed(() => store.riskEvent)
const lossGrids = computed(() => riskEvent.value?.gridCells ?? [])
const heatMetric = ref<GridHeatMetric>('pga')
const calculating = ref(false)
const calculated = ref(false)

const lossFiles = computed(() => {
  const stem = riskEvent.value?.lossFileStem || 'Case2005_Chiba_Banyan'
  return {
    typhoon: `${stem}_Typhoon_loss.csv`,
    earthquake: `${stem}_Earthquake_loss.csv`,
    coupled: `${stem}_Coupled_loss.csv`,
  } as const
})

async function handleCalculate() {
  calculating.value = true
  calculated.value = false
  try {
    const caseId = encodeURIComponent(riskEvent.value?.id || '')
    const response = await fetch(`/api/calculate-loss?caseId=${caseId}`, { method: 'POST' })
    const result = await response.json() as { ok?: boolean; error?: string }
    if (!response.ok || !result.ok) throw new Error(result.error || 'Calculation failed')
    calculated.value = true
  } catch (err) {
    store.riskError = err instanceof Error ? err.message : 'Calculation failed'
  } finally {
    calculating.value = false
  }
}

async function handleDownload(kind: 'typhoon' | 'earthquake' | 'coupled') {
  const filename = lossFiles.value[kind]
  const response = await fetch(`/data/risk-loss/${filename}`)
  if (!response.ok) return
  const text = await response.text()
  const values = text.split(/\r?\n/).slice(1).map(Number).filter(Number.isFinite)
  downloadLossCsv(filename, values)
}

onMounted(() => {
  void store.ensureRiskCase()
})
</script>

<template>
  <div class="page">
    <RiskHeader
      :calculating="calculating"
      :calculated="calculated"
      @calculate="handleCalculate"
      @download="handleDownload"
    />

    <div class="risk-map-row">
      <JapanMap
        :event="riskEvent"
        :loss-grids="lossGrids"
        :grid-half-deg="riskEvent?.gridHalfDeg"
        :heat-metric="heatMetric"
        @update:heat-metric="heatMetric = $event"
      />
      <LossResultCharts :file-stem="riskEvent?.lossFileStem" />
    </div>
  </div>
</template>
