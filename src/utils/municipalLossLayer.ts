import L from 'leaflet'
import type { FeatureCollection } from 'geojson'
import type { RiskRegion } from '../types'
import { formatJpy } from './formatters'

/** 损失强度 0–1 → 填色 */
export function lossColor(t: number): string {
  const x = Math.max(0, Math.min(1, t))
  if (x < 0.25) {
    const u = x / 0.25
    return `rgb(${Math.round(56 + 40 * u)}, ${Math.round(120 + 80 * u)}, ${Math.round(220 - 40 * u)})`
  }
  if (x < 0.5) {
    const u = (x - 0.25) / 0.25
    return `rgb(${Math.round(96 + 100 * u)}, ${Math.round(200 - 40 * u)}, ${Math.round(180 - 100 * u)})`
  }
  if (x < 0.75) {
    const u = (x - 0.5) / 0.25
    return `rgb(${Math.round(196 + 40 * u)}, ${Math.round(160 - 80 * u)}, ${Math.round(80 - 40 * u)})`
  }
  const u = (x - 0.75) / 0.25
  return `rgb(${Math.round(236 - 20 * u)}, ${Math.round(80 - 50 * u)}, ${Math.round(40 - 20 * u)})`
}

function regionDetailHtml(region: RiskRegion, rank: number): string {
  const loss = region.lossJpy ?? region.lossIndex
  return `
    <div class="muni-popup">
      <p class="muni-popup-title">${region.name}</p>
      <p class="muni-popup-row"><span>Coupled loss</span><strong>${formatJpy(loss)}</strong></p>
      <p class="muni-popup-row"><span>Rank</span><strong>${rank}</strong></p>
      <p class="muni-popup-row"><span>Population</span><strong>${region.population.toLocaleString()}</strong></p>
      <p class="muni-popup-row"><span>Mean PGA</span><strong>${region.meanPgaGal.toFixed(1)} gal</strong></p>
      <p class="muni-popup-row"><span>Mean wind</span><strong>${region.meanWindMs.toFixed(1)} m/s</strong></p>
    </div>
  `
}

const MUNI_DETAIL_TOOLTIP_OPTS: L.TooltipOptions = {
  sticky: true,
  opacity: 1,
  className: 'muni-loss-tooltip-pane',
  direction: 'top',
}

function bindRegionDetailTooltip(layer: L.Layer, region: RiskRegion, rank: number) {
  layer.bindTooltip(regionDetailHtml(region, rank), MUNI_DETAIL_TOOLTIP_OPTS)
}

function buildLossMaps(regions: RiskRegion[]) {
  const maxLoss = Math.max(...regions.map((r) => r.lossJpy ?? r.lossIndex), 1)
  const sorted = [...regions].sort((a, b) => (b.lossJpy ?? b.lossIndex) - (a.lossJpy ?? a.lossIndex))
  const rankMap = new Map(sorted.map((r, i) => [r.id, i + 1]))
  const byId = new Map(regions.map((r) => [r.id, r]))
  return { maxLoss, rankMap, byId }
}

/** 市町村行政区块着色（GeoJSON 面） */
export function addMunicipalChoropleth(
  geojson: FeatureCollection,
  regions: RiskRegion[],
  layer: L.LayerGroup,
): [number, number][] {
  const { maxLoss, rankMap, byId } = buildLossMaps(regions)
  const bounds: [number, number][] = []

  L.geoJSON(geojson, {
    style: (feature) => {
      const name = feature?.properties?.name ?? feature?.properties?.id
      const region = name ? byId.get(String(name)) : undefined
      const t = region ? (region.lossJpy ?? region.lossIndex) / maxLoss : 0
      return {
        fillColor: lossColor(t),
        fillOpacity: region ? 0.58 + t * 0.28 : 0.08,
        color: '#475569',
        weight: 0.9,
        opacity: 0.85,
      }
    },
    onEachFeature: (feature, featLayer) => {
      const name = String(feature?.properties?.name ?? feature?.properties?.id ?? '')
      const region = byId.get(name)
      if (!region) return

      bindRegionDetailTooltip(featLayer, region, rankMap.get(region.id) ?? 0)

      const fb = (featLayer as L.Polygon).getBounds?.()
      if (fb?.isValid()) {
        bounds.push([fb.getSouth(), fb.getWest()], [fb.getNorth(), fb.getEast()])
      }
    },
  }).addTo(layer)

  // 若 geoJSON bounds 收集失败，回退到质心
  if (!bounds.length) {
    regions.forEach((r) => {
      if (r.lat != null && r.lng != null) bounds.push([r.lat, r.lng])
    })
  }

  return bounds
}

/** 市町村质心气泡（备选展示） */
export function addMunicipalBubbles(
  regions: RiskRegion[],
  layer: L.LayerGroup,
): [number, number][] {
  const valid = regions.filter(
    (r) => r.lat != null && r.lng != null && Number.isFinite(r.lossJpy ?? r.lossIndex),
  )
  if (!valid.length) return []

  const { maxLoss, rankMap } = buildLossMaps(regions)
  const bounds: [number, number][] = []

  valid.forEach((region) => {
    const lat = region.lat!
    const lng = region.lng!
    const t = (region.lossJpy ?? region.lossIndex) / maxLoss
    const radius = 1800 + Math.sqrt(t) * 8500

    L.circle([lat, lng], {
      radius,
      color: lossColor(t),
      fillColor: lossColor(t),
      fillOpacity: 0.42 + t * 0.38,
      opacity: 0.75,
      weight: 1.2,
      interactive: true,
    })
      .bindTooltip(regionDetailHtml(region, rankMap.get(region.id) ?? 0), MUNI_DETAIL_TOOLTIP_OPTS)
      .addTo(layer)

    bounds.push([lat, lng])
  })

  return bounds
}
