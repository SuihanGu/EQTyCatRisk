import L from 'leaflet'
import type { CouplingEvent } from '../types'
import { formatCouplingType } from './formatters'
import { pairHoverHtml, typhoonCodeFromZid } from './pairLabel'

function epicenterPopupHtml(event: CouplingEvent): string {
  const { lat, lng } = event.epicenter
  const tc = typhoonCodeFromZid(event.id)
  const type = formatCouplingType(event.couplingType)
  const depth =
    event.depthKm != null && Number.isFinite(event.depthKm)
      ? `<p class="epicenter-popup-coord">Focal depth ${event.depthKm.toFixed(0)} km</p>`
      : ''
  return `
    <div class="epicenter-popup">
      <p class="epicenter-popup-title">Epicenter</p>
      <p class="epicenter-popup-mag">Mw ${event.magnitude.toFixed(1)}</p>
      <p class="epicenter-popup-coord">${lat.toFixed(2)}°N · ${lng.toFixed(2)}°E</p>
      ${depth}
      <p class="epicenter-popup-coord">Coupled typhoon ${tc}${event.couplingType ? ` · ${type}` : ''}</p>
    </div>
  `
}

function createEpicenterIcon(compact = false): L.DivIcon {
  const size = compact ? 28 : 52
  const anchor = size / 2
  return L.divIcon({
    className: `epicenter-marker-wrap${compact ? ' is-compact' : ''}`,
    html: `
      <div class="epicenter-marker${compact ? ' is-compact' : ''}" aria-hidden="true">
        ${
          compact
            ? ''
            : `
        <span class="epicenter-ring ring-1"></span>
        <span class="epicenter-ring ring-2"></span>
        <span class="epicenter-halo"></span>`
        }
        <span class="epicenter-diamond"></span>
        <span class="epicenter-dot"></span>
      </div>
    `,
    iconSize: [size, size],
    iconAnchor: [anchor, anchor],
    popupAnchor: [0, -Math.round(size * 0.4)],
  })
}

export function addEpicenterLayers(
  event: CouplingEvent,
  layer: L.LayerGroup,
  options?: {
    compact?: boolean
    interactive?: boolean
    onSelect?: (id: string) => void
  },
) {
  const { lat, lng } = event.epicenter
  const magnitude = event.magnitude
  const compact = options?.compact ?? false
  const interactive = options?.interactive ?? true

  if (!compact) {
    ;[magnitude * 9200, magnitude * 5800, magnitude * 3200].forEach((radius, index) => {
      L.circle([lat, lng], {
        radius,
        color: '#b91c1c',
        fillColor: '#ef4444',
        fillOpacity: 0.045 + index * 0.015,
        weight: 1.2,
        opacity: 0.22 + index * 0.08,
        dashArray: index === 0 ? undefined : '6 8',
        interactive: false,
      }).addTo(layer)
    })
  }

  const marker = L.marker([lat, lng], {
    icon: createEpicenterIcon(compact),
    zIndexOffset: compact ? 400 : 1000,
    interactive,
  })

  marker.bindTooltip(
    pairHoverHtml({
      zid: event.id,
      magnitude: event.magnitude,
      couplingType: event.couplingType,
      eqTime: event.eqTime,
      tcTime: event.tcTime,
      windMs: event.windMs,
      lat,
      lng,
    }),
    {
      direction: 'top',
      offset: [0, compact ? -12 : -18],
      opacity: 0.96,
      className: 'pair-hover-tooltip',
      sticky: false,
    },
  )

  marker.bindPopup(epicenterPopupHtml(event), { className: 'epicenter-popup-pane' })

  if (options?.onSelect) {
    marker.on('click', () => options.onSelect?.(event.id))
  }

  marker.addTo(layer)
  return marker
}
