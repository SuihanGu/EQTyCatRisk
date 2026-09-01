<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useEventStore } from '../stores/eventStore'
import RiskHeader from '../components/RiskHeader.vue'
import JapanMap from '../components/JapanMap.vue'
import LossResultCharts from '../components/LossResultCharts.vue'

const store = useEventStore()

const riskEvent = computed(() => store.riskEvent)
const lossGrids = computed(() => riskEvent.value?.gridCells ?? [])

onMounted(() => {
  void store.ensureRiskCase()
})
</script>

<template>
  <div class="page">
    <RiskHeader />

    <div class="risk-map-row">
      <JapanMap
        :event="riskEvent"
        :loss-grids="lossGrids"
        :grid-half-deg="riskEvent?.gridHalfDeg"
      />
      <LossResultCharts />
    </div>
  </div>
</template>
