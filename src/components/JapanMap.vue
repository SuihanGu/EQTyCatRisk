<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { CouplingCatalogItem, CouplingEvent, RiskGridCell } from '../types'
import { JAPAN_MAP_CENTER, JAPAN_MAP_ZOOM, JAPAN_VIEW_BOUNDS } from '../data/prefectures'
import { addEpicenterLayers } from '../utils/epicenterMarker'
import { typhoonCodeFromZid } from '../utils/pairLabel'
import { catalogItemToMapEvent } from '../utils/generator'
import { addGridLossLayer } from '../utils/gridLossLayer'
import { formatCouplingType } from '../utils/formatters'
import { addPathDirectionArrows } from '../utils/pathArrows'

const props = defineProps<{
  /** 当前选中事件（详情高亮 / 风险页单事件） */
  event?: CouplingEvent | null
  /** 全部耦合事件目录：有值时地图同时绘制全部震源与完整路径 */
  events?: CouplingCatalogItem[]
  selectedId?: string
  /** 网格耦合损失 JPY（风险页） */
  lossGrids?: RiskGridCell[]
  gridHalfDeg?: number
}>()

const emit = defineEmits<{
  select: [id: string]
}>()

const mapContainer = ref<HTMLElement | null>(null)
let map: L.Map | null = null
let overviewLayer: L.LayerGroup | null = null
let selectedLayer: L.LayerGroup | null = null
let lossLayer: L.LayerGroup | null = null
let resizeObserver: ResizeObserver | null = null
let didFitAll = false
let didFitLoss = false

/** 无 API Key 的栅格底图（CARTO voyager 现已水印 “API KEY REQUIRED”） */
const TILE_SOURCES = [
  {
    name: 'GSI',
    url: 'https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png',
    options: {
      maxZoom: 18,
      maxNativeZoom: 18,
    },
    credit: '© GSI Japan',
  },
  {
    name: 'GSI-std',
    url: 'https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png',
    options: {
      maxZoom: 18,
      maxNativeZoom: 18,
    },
    credit: '© GSI Japan',
  },
  {
    name: 'Esri',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    options: {
      maxZoom: 19,
    },
    credit: '© Esri',
  },
  {
    name: 'OSM',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: {
      maxZoom: 19,
    },
    credit: '© OpenStreetMap',
  },
]

const activeTileCredit = ref(TILE_SOURCES[0]!.credit)

function addTileLayer(targetMap: L.Map) {
  let sourceIndex = 0
  let currentLayer: L.TileLayer | null = null
  let errorCount = 0

  const trySource = (index: number) => {
    if (index >= TILE_SOURCES.length) return
    const source = TILE_SOURCES[index]!
    sourceIndex = index
    errorCount = 0
    activeTileCredit.value = source.credit

    if (currentLayer) {
      targetMap.removeLayer(currentLayer)
      currentLayer = null
    }

    const layer = L.tileLayer(source.url, {
      ...source.options,
      attribution: '',
    })

    layer.on('tileerror', () => {
      errorCount += 1
      // 连续多块失败再切换，避免偶发失败误判
      if (errorCount >= 4 && sourceIndex === index) {
        trySource(index + 1)
      }
    })

    layer.on('load', () => {
      errorCount = 0
    })

    layer.addTo(targetMap)
    currentLayer = layer
  }

  trySource(0)
}

function initMap() {
  if (!mapContainer.value || map) return

  map = L.map(mapContainer.value, {
    center: JAPAN_MAP_CENTER,
    zoom: JAPAN_MAP_ZOOM,
    scrollWheelZoom: true,
    preferCanvas: true,
    attributionControl: false,
    zoomControl: true,
  })

  addTileLayer(map)
  lossLayer = L.layerGroup().addTo(map)
  overviewLayer = L.layerGroup().addTo(map)
  selectedLayer = L.layerGroup().addTo(map)
  renderAll()

  requestAnimationFrame(() => map?.invalidateSize())
}

function selectPair(id: string) {
  emit('select', id)
}

function drawOverviewPath(item: CouplingCatalogItem, layer: L.LayerGroup, muted: boolean) {
  const coords = item.typhoonPath.map((p) => [p.lat, p.lng] as [number, number])
  if (coords.length < 2) return

  const color = muted ? '#94a3b8' : '#0ea5a4'
  const line = L.polyline(coords, {
    color,
    weight: muted ? 1.2 : 2.2,
    opacity: muted ? 0.28 : 0.55,
    interactive: true,
  })

  line.bindTooltip(
    `Typhoon ${typhoonCodeFromZid(item.id)} · Coupled Mw ${item.magnitude.toFixed(1)} · ${formatCouplingType(item.couplingType)}`,
    { sticky: true, opacity: 0.92 },
  )
  line.on('click', () => selectPair(item.id))
  line.addTo(layer)

  // 箭头：时间早 → 时间近；未选中路径稀疏一些
  addPathDirectionArrows(coords, layer, {
    color: muted ? '#64748b' : '#0d9488',
    every: muted ? Math.max(4, Math.floor(coords.length / 5)) : Math.max(2, Math.floor(coords.length / 10)),
    maxArrows: muted ? 5 : 12,
    size: muted ? 16 : 20,
    opacity: muted ? 0.7 : 1,
  })
}

function drawSelectedDetail(event: CouplingEvent, layer: L.LayerGroup) {
  const pathCoords = event.typhoonPath.map((p) => [p.lat, p.lng] as [number, number])
  const boundsPoints: [number, number][] = []

  if (pathCoords.length > 1) {
    L.polyline(pathCoords, {
      color: '#0f766e',
      weight: 4,
      opacity: 0.95,
      interactive: false,
    }).addTo(layer)

    addPathDirectionArrows(pathCoords, layer, {
      color: '#0f766e',
      every: Math.max(1, Math.floor(pathCoords.length / 12)),
      maxArrows: 18,
      size: 24,
      opacity: 1,
    })

    const step = Math.max(1, Math.floor(pathCoords.length / 8))
    pathCoords.forEach((coord, i) => {
      const isEdge = i === 0 || i === pathCoords.length - 1
      if (!isEdge && i % step !== 0) return

      L.circleMarker(coord, {
        radius: isEdge ? 5 : 3.5,
        color: '#0ea5a4',
        fillColor: i === pathCoords.length - 1 ? '#f97316' : '#0ea5a4',
        fillOpacity: 0.9,
        weight: 1,
        interactive: false,
      })
        .bindTooltip(
          i === 0
            ? 'Track start (earlier)'
            : i === pathCoords.length - 1
              ? 'Track end (later)'
              : `Track point ${i + 1}${event.typhoonPath[i]?.windMs != null ? ` · ${event.typhoonPath[i]!.windMs} m/s` : ''}`,
        )
        .addTo(layer)
    })

    boundsPoints.push(...pathCoords)
  }

  const tc = event.typhoonAtCoupling
  if (tc) {
    if (event.r34Km != null && event.r34Km > 0) {
      L.circle([tc.lat, tc.lng], {
        radius: event.r34Km * 1000,
        color: '#0d9488',
        fillColor: '#14b8a6',
        fillOpacity: 0.1,
        weight: 1.5,
        dashArray: '4 6',
        interactive: false,
      })
        .bindTooltip(`R34 · ${event.r34Km.toFixed(1)} km`)
        .addTo(layer)
    }

    L.circleMarker([tc.lat, tc.lng], {
      radius: 8,
      color: '#0f766e',
      fillColor: '#2dd4bf',
      fillOpacity: 0.95,
      weight: 2,
      interactive: false,
    })
      .bindPopup(
        `<strong>Typhoon center at coupling · ${typhoonCodeFromZid(event.id)}</strong><br/>${tc.lat.toFixed(2)}°N, ${tc.lng.toFixed(2)}°E<br/>Wind ${event.windMs.toFixed(1)} m/s`,
      )
      .addTo(layer)

    boundsPoints.push([tc.lat, tc.lng])
  }

  addEpicenterLayers(event, layer, { compact: false })
  boundsPoints.push([event.epicenter.lat, event.epicenter.lng])

  return boundsPoints
}

function renderOverview() {
  if (!map || !overviewLayer) return
  overviewLayer.clearLayers()

  const catalog = props.events ?? []
  if (!catalog.length) return

  const selectedId = props.selectedId || props.event?.id
  const japanBounds = L.latLngBounds(JAPAN_VIEW_BOUNDS)

  catalog.forEach((item) => {
    const muted = !!selectedId && item.id !== selectedId
    drawOverviewPath(item, overviewLayer!, muted)

    // 非选中：小震源点；选中交由 selectedLayer 画大标记，避免重复
    if (item.id === selectedId) return

    const asEvent = catalogItemToMapEvent(item)
    addEpicenterLayers(asEvent, overviewLayer!, {
      compact: true,
      onSelect: selectPair,
    })
  })

  if (!didFitAll) {
    // 框定日本列岛，避免完整台风远洋路径把视野拉得过小
    map.fitBounds(japanBounds, { padding: [16, 16], maxZoom: 7.2 })
    didFitAll = true
  }
}

function renderSelected() {
  if (!map || !selectedLayer) return
  selectedLayer.clearLayers()

  const catalog = props.events ?? []
  const selectedId = props.selectedId || props.event?.id

  // 总览模式：高亮选中一对
  if (catalog.length && selectedId) {
    const item = catalog.find((e) => e.id === selectedId)
    if (!item) return
    const event = props.event?.id === selectedId ? props.event : catalogItemToMapEvent(item)
    drawSelectedDetail(event, selectedLayer)
    return
  }

  // 风险页等：仅单事件
  if (!catalog.length && props.event) {
    const bounds = drawSelectedDetail(props.event, selectedLayer)
    // 有市町村损失层时已在 renderLoss 中框选北海道
    if (props.lossGrids?.length) return

    const japanBounds = L.latLngBounds(JAPAN_VIEW_BOUNDS)
    if (bounds.length >= 2) {
      const local = bounds.filter(([lat, lng]) => japanBounds.contains([lat, lng]))
      const focusPoints = local.length >= 2 ? local : [[props.event.epicenter.lat, props.event.epicenter.lng] as [number, number]]
      if (focusPoints.length >= 2) {
        map.fitBounds(L.latLngBounds(focusPoints), { padding: [40, 40], maxZoom: 8 })
      } else if (focusPoints.length === 1) {
        map.setView(focusPoints[0]!, 7)
      } else {
        map.fitBounds(japanBounds, { padding: [20, 20], maxZoom: 7 })
      }
    } else if (bounds.length === 1) {
      map.setView(bounds[0]!, 7)
    } else {
      map.fitBounds(japanBounds, { padding: [20, 20], maxZoom: 7 })
    }
  }
}

function renderLoss() {
  if (!map || !lossLayer) return
  lossLayer.clearLayers()

  const grids = props.lossGrids ?? []
  if (!grids.length) return

  const bounds = addGridLossLayer(grids, lossLayer, props.gridHalfDeg ?? 0.0041666667)

  if (!didFitLoss && !props.events?.length && bounds.length >= 2) {
    const fit = L.latLngBounds(bounds)
    if (props.event) {
      fit.extend([props.event.epicenter.lat, props.event.epicenter.lng])
    }
    map.fitBounds(fit, { padding: [32, 32], maxZoom: 8.5 })
    didFitLoss = true
  }

  requestAnimationFrame(() => map?.invalidateSize())
}

function renderAll() {
  renderLoss()
  renderOverview()
  renderSelected()
}

watch(
  () =>
    [props.events?.length, props.selectedId, props.event?.id, props.lossGrids?.length] as const,
  () => {
    didFitLoss = false
    renderAll()
  },
)

watch(
  () => props.event,
  () => {
    if (!(props.events?.length)) renderSelected()
  },
  { deep: true },
)

watch(
  () => props.lossGrids,
  () => renderLoss(),
  { deep: true },
)

onMounted(async () => {
  await nextTick()
  initMap()

  if (mapContainer.value) {
    resizeObserver = new ResizeObserver(() => map?.invalidateSize())
    resizeObserver.observe(mapContainer.value)
  }

  setTimeout(() => map?.invalidateSize(), 200)
  setTimeout(() => map?.invalidateSize(), 600)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  map?.remove()
  map = null
  overviewLayer = null
  selectedLayer = null
  lossLayer = null
})
</script>

<template>
  <section class="map-panel">
    <div class="map-panel-head">
      <h3>{{ lossGrids?.length ? 'Grid coupled loss · Hokkaido' : 'Japan map' }}</h3>
      <div class="map-panel-head-right">
        <span class="map-badge">
          {{
            events?.length
              ? `All ${events.length} pairs · Hover epicenter for typhoon`
              : lossGrids?.length
                ? `${lossGrids.length.toLocaleString()} loss grids`
                : activeTileCredit
          }}
        </span>
      </div>
    </div>
    <div
      ref="mapContainer"
      class="map-container"
      :class="lossGrids?.length ? 'map-container--heatmap' : 'map-container--tall'"
    />
    <div v-if="lossGrids?.length" class="heat-legend">
      <span class="heat-legend-label">Coupled loss (JPY)</span>
      <div class="heat-legend-bar" />
      <span>Low</span>
      <span>High</span>
    </div>
    <p v-if="!(events?.length || event)" class="map-hint">
      After the local catalog loads, all epicenters and full typhoon tracks are shown. Select a pair for details.
    </p>
    <p v-else-if="events?.length" class="map-hint">
      Gray tracks/markers are all coupling pairs. Click an epicenter or track to select one. Hover an epicenter to see the typhoon ID.
      <span class="map-credit">Basemap {{ activeTileCredit }}</span>
    </p>
    <p v-else class="map-hint">
      <template v-if="lossGrids?.length">
        Grid cells colored by Coupled_Loss_with_Other_JPY (JPY). Hover for details.
      </template>
      <template v-else>Loading grid losses…</template>
      <span class="map-credit">Basemap {{ activeTileCredit }}</span>
    </p>
  </section>
</template>
