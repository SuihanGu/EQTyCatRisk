<script setup lang="ts">
import { computed } from 'vue'
import type { CouplingEvent } from '../types'

const props = defineProps<{
  event: CouplingEvent | null | undefined
}>()

const rows = computed(() => {
  const event = props.event
  if (!event) return []

  const list: { label: string; value: string; unit?: string }[] = [
    { label: 'Magnitude', value: event.magnitude.toFixed(2), unit: 'Mw' },
    { label: 'Wind speed', value: event.windMs.toFixed(1), unit: 'm/s' },
  ]

  if (event.r34Km != null) {
    list.push({ label: 'R34', value: event.r34Km.toFixed(1), unit: 'km' })
  }
  if (event.depthKm != null) {
    list.push({ label: 'Focal depth', value: event.depthKm.toFixed(0), unit: 'km' })
  }
  if (event.distanceKm != null) {
    list.push({ label: 'EQ–TC distance', value: Math.abs(event.distanceKm).toFixed(1), unit: 'km' })
  }
  if (event.dtHours != null) {
    list.push({ label: '|dt|', value: Math.abs(event.dtHours).toFixed(1), unit: 'h' })
  }

  if (event.eqTime) {
    list.push({ label: 'EQ time (UTC)', value: event.eqTime })
  }

  list.push({
    label: 'Epicenter',
    value: `${event.epicenter.lat.toFixed(2)}°N, ${event.epicenter.lng.toFixed(2)}°E`,
  })

  return list
})
</script>

<template>
  <section class="chart-panel param-list-panel">
    <div class="chart-panel-head">
      <h3>Coupling info</h3>
    </div>

    <ul v-if="rows.length" class="param-list">
      <li v-for="row in rows" :key="row.label" class="param-list-row">
        <span class="param-label">{{ row.label }}</span>
        <span class="param-value">
          {{ row.value }}
          <span v-if="row.unit" class="param-unit">{{ row.unit }}</span>
        </span>
      </li>
    </ul>
    <p v-else class="param-list-empty">No data</p>
  </section>
</template>
