import type { CouplingCatalogItem, CouplingEvent, RiskCaseEvent } from '../types'
import { loadCouplingCatalog } from '../services/couplingData'
import { loadRiskCase, loadRiskGridCells } from '../services/riskData'
import { catalogItemToEvent } from '../utils/generator'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useEventStore = defineStore('event', () => {
  const currentEvent = ref<CouplingEvent | null>(null)
  const selectedId = ref<string>('')
  const catalog = ref<CouplingCatalogItem[]>([])
  const catalogLoaded = ref(false)
  const catalogError = ref<string | null>(null)
  const loading = ref(false)

  const riskCase = ref<RiskCaseEvent | null>(null)
  const riskLoaded = ref(false)
  const riskError = ref<string | null>(null)
  const historicalId = ref('')

  const mapEvent = computed(() => currentEvent.value)

  const selectedIndex = computed(() =>
    catalog.value.findIndex((item) => item.id === selectedId.value),
  )

  const historicalEvents = computed(() => (riskCase.value ? [riskCase.value] : []))

  const riskEvent = computed(() => {
    if (!riskCase.value) return null
    if (historicalId.value && riskCase.value.id !== historicalId.value) return riskCase.value
    return riskCase.value
  })

  function applyCatalogItem(item: CouplingCatalogItem) {
    selectedId.value = item.id
    currentEvent.value = catalogItemToEvent(item)
  }

  async function ensureCatalog() {
    if (catalogLoaded.value) return catalog.value
    loading.value = true
    catalogError.value = null
    try {
      catalog.value = await loadCouplingCatalog()
      catalogLoaded.value = true
      return catalog.value
    } catch (err) {
      catalogError.value = err instanceof Error ? err.message : 'Failed to load coupling events'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function ensureRiskCase() {
    if (riskLoaded.value && riskCase.value) {
      if (!riskCase.value.gridCells?.length) {
        void loadRiskGridCells(riskCase.value)
          .then((cells) => {
            if (!riskCase.value) return
            riskCase.value = { ...riskCase.value, gridCells: cells }
          })
          .catch((err) => {
            riskError.value = err instanceof Error ? err.message : 'Failed to load grid losses'
          })
      }
      return riskCase.value
    }
    riskError.value = null
    try {
      const event = await loadRiskCase()
      riskCase.value = event
      riskLoaded.value = true
      if (!historicalId.value) historicalId.value = event.id

      if (!event.gridCells?.length) {
        void loadRiskGridCells(event)
          .then((cells) => {
            if (!riskCase.value) return
            riskCase.value = { ...riskCase.value, gridCells: cells }
          })
          .catch((err) => {
            riskError.value = err instanceof Error ? err.message : 'Failed to load grid losses'
          })
      }
      return riskCase.value
    } catch (err) {
      riskError.value = err instanceof Error ? err.message : 'Failed to load risk case'
      throw err
    }
  }

  async function loadInitialEvent() {
    const items = await ensureCatalog()
    if (!items.length) {
      throw new Error('Coupling catalog is empty. Check public/data/coupling-events.json')
    }
    if (!currentEvent.value) {
      applyCatalogItem(items[0]!)
    }
  }

  async function selectEventById(id: string) {
    const items = await ensureCatalog()
    const item = items.find((e) => e.id === id)
    if (!item) {
      throw new Error(`Event not found: ${id}`)
    }
    applyCatalogItem(item)
  }

  async function selectAdjacent(delta: number) {
    const items = await ensureCatalog()
    if (!items.length) return
    const current = selectedIndex.value
    const next = current < 0 ? 0 : (current + delta + items.length) % items.length
    applyCatalogItem(items[next]!)
  }

  function setHistorical(id: string) {
    historicalId.value = id
  }

  return {
    currentEvent,
    selectedId,
    selectedIndex,
    catalog,
    catalogLoaded,
    catalogError,
    loading,
    historicalId,
    historicalEvents,
    riskCase,
    riskLoaded,
    riskError,
    mapEvent,
    riskEvent,
    ensureCatalog,
    ensureRiskCase,
    loadInitialEvent,
    selectEventById,
    selectAdjacent,
    setHistorical,
  }
})
