<script setup lang="ts">
import { computed } from 'vue'
import type { CouplingEvent } from '../types'

const props = defineProps<{
  event: CouplingEvent | null | undefined
}>()

const panels = computed(() => {
  const loss = props.event?.structureLoss
  if (!loss) {
    return [
      { key: 'wood', title: 'Wood', desc: 'Residential & low-rise timber', value: 0, unit: 'M JPY', color: '#92400e', pct: 0 },
      { key: 'steel', title: 'Steel', desc: 'Industrial & long-span', value: 0, unit: 'M JPY', color: '#475569', pct: 0 },
      { key: 'rc', title: 'RC', desc: 'Frame & shear wall', value: 0, unit: 'M JPY', color: '#1e40af', pct: 0 },
      { key: 'masonry', title: 'Masonry', desc: 'Brick & masonry walls', value: 0, unit: 'M JPY', color: '#7c2d12', pct: 0 },
    ]
  }

  const total = loss.wood + loss.steel + loss.rc + loss.masonry

  return [
    { key: 'wood', title: 'Wood', desc: 'Residential & low-rise timber', value: loss.wood, unit: 'M JPY', color: '#92400e', pct: Math.round((loss.wood / total) * 100) },
    { key: 'steel', title: 'Steel', desc: 'Industrial & long-span', value: loss.steel, unit: 'M JPY', color: '#475569', pct: Math.round((loss.steel / total) * 100) },
    { key: 'rc', title: 'RC', desc: 'Frame & shear wall', value: loss.rc, unit: 'M JPY', color: '#1e40af', pct: Math.round((loss.rc / total) * 100) },
    { key: 'masonry', title: 'Masonry', desc: 'Brick & masonry walls', value: loss.masonry, unit: 'M JPY', color: '#7c2d12', pct: Math.round((loss.masonry / total) * 100) },
  ]
})
</script>

<template>
  <section class="loss-panels">
    <article
      v-for="panel in panels"
      :key="panel.key"
      class="loss-card"
      :style="{ '--accent': panel.color }"
    >
      <div class="loss-card-top">
        <div>
          <h4>{{ panel.title }}</h4>
          <p class="loss-desc">{{ panel.desc }}</p>
        </div>
        <span class="loss-pct">{{ panel.pct }}%</span>
      </div>
      <p class="loss-value">{{ panel.value.toLocaleString() }}</p>
      <p class="loss-unit">{{ panel.unit }}</p>
    </article>
  </section>
</template>
