<script setup lang="ts">
import { useEventStore } from '../stores/eventStore'

const store = useEventStore()

function onHistoricalChange(e: Event) {
  store.setHistorical((e.target as HTMLSelectElement).value)
}
</script>

<template>
  <header class="page-header risk-header">
    <label class="select-field risk-header-field">
      <span class="select-label">Historical event</span>
      <select
        :value="store.historicalId"
        :disabled="!store.historicalEvents.length"
        @change="onHistoricalChange"
      >
        <option v-if="!store.historicalEvents.length" value="">Loading…</option>
        <option v-for="evt in store.historicalEvents" :key="evt.id" :value="evt.id">
          {{ evt.label || `${evt.year} · ${evt.id} · M${evt.magnitude.toFixed(1)}` }}
        </option>
      </select>
    </label>

    <h1 class="risk-header-kicker">Risk Assessment</h1>

    <p v-if="store.riskError" class="risk-header-error">{{ store.riskError }}</p>
  </header>
</template>
