<script setup lang="ts">
import type { CouplingCatalogItem } from '../types'
import { formatCouplingType } from '../utils/formatters'

defineProps<{
  options: CouplingCatalogItem[]
  modelValue: string
  loading?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [id: string]
  prev: []
  next: []
}>()

function shortLabel(item: CouplingCatalogItem): string {
  const tc = item.id.includes('__TC-') ? item.id.split('__TC-')[1] : item.id
  const year = item.eqTime?.slice(0, 4) || item.year || '—'
  const type = formatCouplingType(item.couplingType)
  return `${year} · ${tc} · ${type} · Mw ${item.magnitude.toFixed(1)}`
}

function onChange(e: Event) {
  const value = (e.target as HTMLSelectElement).value
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="event-picker">
    <button
      type="button"
      class="btn-nav"
      :disabled="disabled || loading || options.length === 0"
      title="Previous"
      @click="emit('prev')"
    >
      ‹
    </button>
    <select
      class="event-select"
      :value="modelValue"
      :disabled="disabled || loading || options.length === 0"
      @change="onChange"
    >
      <option v-if="!options.length" value="">No events</option>
      <option v-for="item in options" :key="item.id" :value="item.id">
        {{ shortLabel(item) }}
      </option>
    </select>
    <button
      type="button"
      class="btn-nav"
      :disabled="disabled || loading || options.length === 0"
      title="Next"
      @click="emit('next')"
    >
      ›
    </button>
  </div>
</template>
