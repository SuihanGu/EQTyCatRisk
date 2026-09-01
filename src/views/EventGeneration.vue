<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useEventStore } from '../stores/eventStore'
import EventHeader from '../components/EventHeader.vue'
import GenerateButton from '../components/GenerateButton.vue'
import JapanMap from '../components/JapanMap.vue'
import EarthquakeChart from '../components/EarthquakeChart.vue'
import TyphoonChart from '../components/TyphoonChart.vue'

const store = useEventStore()

const displayEvent = computed(() => store.mapEvent)

async function handleSelect(id: string) {
  try {
    await store.selectEventById(id)
  } catch {
    // catalogError 已在 store 中记录
  }
}

async function handlePrev() {
  try {
    await store.selectAdjacent(-1)
  } catch {
    // ignore
  }
}

async function handleNext() {
  try {
    await store.selectAdjacent(1)
  } catch {
    // ignore
  }
}

onMounted(() => {
  void store.loadInitialEvent()
})
</script>

<template>
  <div class="page">
    <EventHeader :event="displayEvent">
      <GenerateButton
        :options="store.catalog"
        :model-value="store.selectedId"
        :loading="store.loading"
        :disabled="!!store.catalogError && !store.catalogLoaded"
        @update:model-value="handleSelect"
        @prev="handlePrev"
        @next="handleNext"
      />
    </EventHeader>

    <!-- <p v-if="store.catalogError" class="data-banner error">
      {{ store.catalogError }}
    </p> -->
    <!-- <p v-else-if="store.catalogLoaded" class="data-banner">
      地图已绘制全部 {{ store.catalog.length }} 对耦合（震源 + 完整台风路径）。悬停震源可查看对应台风；点击或用下拉框选择一对查看详情
      <template v-if="store.selectedIndex >= 0">
        · 当前第 {{ store.selectedIndex + 1 }} / {{ store.catalog.length }}
      </template>
    </p> -->

    <div class="risk-map-row">
      <JapanMap
        :event="displayEvent"
        :events="store.catalog"
        :selected-id="store.selectedId"
        @select="handleSelect"
      />

      <div class="charts-row">
        <EarthquakeChart :event="displayEvent" />
        <TyphoonChart :event="displayEvent" />
      </div>
    </div>
  </div>
</template>
