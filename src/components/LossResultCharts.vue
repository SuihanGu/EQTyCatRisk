<script setup lang="ts">
const charts = [
  {
    key: 'coupled',
    title: 'Coupled loss',
    subtitle: 'Coupled loss distribution',
    src: '/data/risk-loss/coupled.png',
    stat: '650.89 M USD · 74.1%',
  },
  {
    key: 'earthquake',
    title: 'Earthquake loss',
    subtitle: 'Earthquake loss distribution',
    src: '/data/risk-loss/earthquake.png',
    stat: '603.34 M USD · 74.6%',
  },
  {
    key: 'typhoon',
    title: 'Typhoon loss',
    subtitle: 'Typhoon loss distribution',
    src: '/data/risk-loss/typhoon.png',
    stat: '0.19 M USD · 76.9%',
  },
] as const
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
