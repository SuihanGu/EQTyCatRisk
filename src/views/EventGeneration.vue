<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useEventStore } from '../stores/eventStore'
import EventHeader from '../components/EventHeader.vue'
import GenerateButton from '../components/GenerateButton.vue'
import JapanMap from '../components/JapanMap.vue'
import EarthquakeChart from '../components/EarthquakeChart.vue'
import TyphoonChart from '../components/TyphoonChart.vue'

const store = useEventStore()

const displayEvent = computed(() => store.mapEvent)
const recognizing = ref(false)
const recognitionDone = ref(false)
const recognitionMessage = ref('')
const downloadUrls = ref<{ coupling: string; tracks: string } | null>(null)

async function handleRecognition() {
  recognizing.value = true
  recognitionDone.value = false
  recognitionMessage.value = 'Recognizing…'
  try {
    const response = await fetch('/api/recognize', { method: 'POST' })
    const result = await response.json() as { ok?: boolean; error?: string; downloads?: { coupling: string; tracks: string } }
    if (!response.ok || !result.ok || !result.downloads) throw new Error(result.error || 'Recognition failed')
    downloadUrls.value = result.downloads
    await store.reloadCatalog()
    recognitionDone.value = true
    recognitionMessage.value = `Recognition complete: ${store.catalog.length} simultaneous events`
  } catch (err) {
    recognitionMessage.value = err instanceof Error ? err.message : 'Recognition failed'
  } finally {
    recognizing.value = false
  }
}

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
      <template #actions>
        <div class="page-actions event-actions">
          <button type="button" class="action-button action-button--primary" :disabled="recognizing" @click="handleRecognition">
            {{ recognizing ? 'Recognizing…' : 'Recognize' }}
          </button>
          <a class="action-button" :class="{ 'action-button--disabled': !downloadUrls }" :href="downloadUrls?.coupling" download>Download coupling information</a>
          <a class="action-button" :class="{ 'action-button--disabled': !downloadUrls }" :href="downloadUrls?.tracks" download>Download complete typhoon tracks</a>
          <span v-if="recognitionMessage" class="action-status">{{ recognitionMessage }}</span>
        </div>
      </template>
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
