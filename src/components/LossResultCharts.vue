<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ fileStem?: string }>()
const stem = () => props.fileStem || 'Case2005_Chiba_Banyan'
const charts = computed(() => [
  {
    key: 'coupled',
    title: 'Coupled loss',
    subtitle: 'Coupled loss distribution',
    src: `/data/risk-loss/${stem()}_Coupled_loss.png`,
    stat: '2,000 simulations',
  },
  {
    key: 'earthquake',
    title: 'Earthquake loss',
    subtitle: 'Earthquake loss distribution',
    src: `/data/risk-loss/${stem()}_Earthquake_loss.png`,
    stat: '2,000 simulations',
  },
  {
    key: 'typhoon',
    title: 'Typhoon loss',
    subtitle: 'Typhoon loss distribution',
    src: `/data/risk-loss/${stem()}_Typhoon_loss.png`,
    stat: '2,000 simulations',
  },
])
</script>

<template>
  <section class="loss-charts-wrap">
    <!-- <header class="section-intro">
      <h2>Loss probability</h2>
      <p>Building loss exceedance curves for coupled, earthquake, and typhoon cases (M USD)</p>
    </header> -->

    <div class="loss-charts">
      <article v-for="chart in charts" :key="chart.key" class="loss-chart-card">
        <header class="loss-chart-card-head">
          <div>
            <h4>{{ chart.title }}</h4>
            <p>{{ chart.subtitle }}</p>
          </div>
          <span class="loss-chart-stat">{{ chart.stat }}</span>
        </header>
        <figure class="loss-chart-figure">
          <img :src="chart.src" :alt="`${chart.title} distribution`" loading="lazy" />
        </figure>
      </article>
    </div>
  </section>
</template>
