<script setup lang="ts">
import type { CouplingEvent } from '../types'

defineProps<{
  event: CouplingEvent | null | undefined
}>()
</script>

<template>
  <header class="page-header page-header--events">
    <slot />
    <div class="metric-group">
      <div class="metric">
        <span class="metric-label">Magnitude</span>
        <span class="metric-value">{{ event ? event.magnitude.toFixed(2) : '—' }}</span>
        <span class="metric-unit">Mw</span>
      </div>
      <div class="metric-divider" />
      <div class="metric">
        <span class="metric-label">Wind</span>
        <span class="metric-value">{{ event ? event.windMs.toFixed(1) : '—' }}</span>
        <span class="metric-unit">m/s</span>
      </div>
      <div class="metric-divider" />
      <div class="metric">
        <span class="metric-label">R34</span>
        <span class="metric-value">{{ event?.r34Km != null ? event.r34Km.toFixed(1) : '—' }}</span>
        <span class="metric-unit">km</span>
      </div>
      <template v-if="event?.depthKm != null">
        <div class="metric-divider" />
        <div class="metric">
          <span class="metric-label">Depth</span>
          <span class="metric-value">{{ event.depthKm.toFixed(0) }}</span>
          <span class="metric-unit">km</span>
        </div>
      </template>
    </div>
  </header>
</template>
