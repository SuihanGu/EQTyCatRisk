<script setup lang="ts">
import { useEventStore } from '../stores/eventStore'

const store = useEventStore()

const props = defineProps<{
  calculating?: boolean
  calculated?: boolean
}>()

const emit = defineEmits<{
  calculate: []
  download: [kind: 'typhoon' | 'earthquake' | 'coupled']
}>()

function onHistoricalChange(e: Event) {
  store.setHistorical((e.target as HTMLSelectElement).value)
}
</script>

<template>
  <header class="page-header risk-header">
    <div class="risk-header-main">
      <label class="select-field risk-header-field">
        <span class="select-label">Historical event</span>
        <select :value="store.historicalId" :disabled="!store.historicalEvents.length" @change="onHistoricalChange">
          <option v-if="!store.historicalEvents.length" value="">Loading…</option>
          <option v-for="evt in store.historicalEvents" :key="evt.id" :value="evt.id">
            {{ evt.label ? evt.label.replace(/\bMw\b/g, 'Mj') : `${evt.year} · ${evt.id} · Mj${evt.magnitude.toFixed(1)}` }}
          </option>
        </select>
      </label>
      <div class="page-actions risk-actions risk-calc-control">
        <button type="button" class="action-button action-button--primary" :disabled="props.calculating" @click="emit('calculate')">
          {{ props.calculating ? 'Calculating…' : 'Calculate' }}
        </button>
      </div>

      <div class="metric-group risk-header-metrics" aria-label="Historical event information">
      <div class="metric">
        <span class="metric-label">Magnitude</span>
        <span class="metric-value">{{ store.riskEvent?.magnitude.toFixed(2) ?? '—' }}</span>
        <span class="metric-unit">Mj</span>
      </div>
      <div class="metric-divider" />
      <div class="metric">
        <span class="metric-label">Depth</span>
        <span class="metric-value">{{ store.riskEvent?.depthKm?.toFixed(0) ?? '—' }}</span>
        <span class="metric-unit">km</span>
      </div>
      <div class="metric-divider" />
      <div class="metric">
        <span class="metric-label">Maximum wind speed</span>
        <span class="metric-value">{{ store.riskEvent?.windKt?.toFixed(1) ?? '—' }}</span>
        <span class="metric-unit">kt</span>
      </div>
      <div class="metric-divider" />
      <div class="metric">
        <span class="metric-label">R30</span>
        <span class="metric-value">{{ store.riskEvent?.r30Km?.toFixed(1) ?? '—' }}</span>
        <span class="metric-unit">km</span>
      </div>
      </div>
    </div>

    <div class="page-actions risk-actions risk-downloads">
      <template v-if="props.calculated">
        <button type="button" class="action-button" @click="emit('download', 'coupled')">Download coupled loss</button>
        <button type="button" class="action-button" @click="emit('download', 'earthquake')">Download earthquake loss</button>
        <button type="button" class="action-button" @click="emit('download', 'typhoon')">Download typhoon loss</button>
      </template>
      <span v-if="props.calculating" class="action-status">Calculating…</span>
      <span v-else-if="props.calculated" class="action-status">Calculation complete: 2,000 simulations</span>
    </div>

    <p v-if="store.riskError" class="risk-header-error">{{ store.riskError }}</p>
  </header>
</template>
