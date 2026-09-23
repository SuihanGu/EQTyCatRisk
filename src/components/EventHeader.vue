<script setup lang="ts">
import type { CouplingEvent } from '../types'

defineProps<{
  event: CouplingEvent | null | undefined
}>()
</script>

<template>
  <header class="page-header page-header--events">
    <div class="event-header-actions"><slot name="actions" /></div>
    <div class="event-header-details">
      <slot />
      <div class="metric-group">
      <div class="metric">
        <span class="metric-label">Magnitude</span>
        <span class="metric-value">{{ event ? event.magnitude.toFixed(2) : '—' }}</span>
        <span class="metric-unit">Mj</span>
      </div>
      <template v-if="event?.depthKm != null">
        <div class="metric-divider" />
        <div class="metric">
          <span class="metric-label">Depth</span>
          <span class="metric-value">{{ event.depthKm.toFixed(0) }}</span>
          <span class="metric-unit">km</span>
        </div>
      </template>
      <div class="metric-divider" />
      <div class="metric">
        <span class="metric-label">Maximum wind speed</span>
        <span class="metric-value">{{ event ? (event.windKt ?? event.windMs * 1.94384).toFixed(1) : '—' }}</span>
        <span class="metric-unit">kt</span>
      </div>
      <div class="metric-divider" />
      <div class="metric">
        <span class="metric-label">R30</span>
        <span class="metric-value">{{ event?.r30Km != null ? event.r30Km.toFixed(1) : '—' }}</span>
        <span class="metric-unit">km</span>
      </div>
      </div>
    </div>
  </header>
</template>
