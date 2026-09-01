import L from 'leaflet'
import type { RiskGridCell } from '../types'
import { formatJpy } from './formatters'
import { lossColor } from './municipalLossLayer'

function cellTooltipHtml(cell: RiskGridCell): string {
  return `
    <div class="muni-popup">
      <p class="muni-popup-title">${cell.name || 'Grid'}</p>
      <p class="muni-popup-row"><span>Coupled loss</span><strong>${formatJpy(cell.lossJpy)}</strong></p>
      <p class="muni-popup-row"><span>Population</span><strong>${(cell.population ?? 0).toLocaleString()}</strong></p>
      ${
        cell.pgaGal != null
          ? `<p class="muni-popup-row"><span>PGA</span><strong>${cell.pgaGal.toFixed(1)} gal</strong></p>`
          : ''
      }
      ${
        cell.windMs != null
          ? `<p class="muni-popup-row"><span>Wind</span><strong>${cell.windMs.toFixed(1)} m/s</strong></p>`
          : ''
      }
      <p class="muni-popup-row"><span>Center</span><strong>${cell.lat.toFixed(4)}°, ${cell.lng.toFixed(4)}°</strong></p>
    </div>
  `
}

type GridLossOptions = {
  halfDeg?: number
  /** 低缩放时抽稀：每个桶只保留损失最大的一格 */
  minZoomFull?: number
}

/**
 * 单 Canvas 绘制全部有损网格，避免数万个 Leaflet Path 导致卡顿。
 */
const GridLossCanvas = L.Layer.extend({
  options: {
    halfDeg: 0.0041666667,
    minZoomFull: 9,
    pane: 'overlayPane',
  } as L.LayerOptions & GridLossOptions,

  initialize(this: any, cells: RiskGridCell[], options?: GridLossOptions) {
    L.setOptions(this, options)
    this._cells = cells
    this._maxLoss = Math.max(...cells.map((c) => c.lossJpy), 1)
    this._tooltip = null as L.Tooltip | null
    // 空间哈希：加速悬停命中
    const half = (options?.halfDeg ?? 0.0041666667) * 2
    this._indexCell = half
    this._index = new Map<string, RiskGridCell[]>()
    for (const cell of cells) {
      const key = `${Math.floor(cell.lat / half)}_${Math.floor(cell.lng / half)}`
      const bucket = this._index.get(key)
      if (bucket) bucket.push(cell)
      else this._index.set(key, [cell])
    }
  },

  onAdd(this: any, map: L.Map) {
    this._map = map
    if (!this._canvas) {
      this._canvas = L.DomUtil.create('canvas', 'leaflet-zoom-animated grid-loss-canvas')
      this._ctx = this._canvas.getContext('2d')
    }
    const pane = map.getPane(this.options.pane) || map.getPanes().overlayPane
    pane.appendChild(this._canvas)

    map.on('moveend', this._redraw, this)
    map.on('zoomend', this._redraw, this)
    map.on('resize', this._redraw, this)
    map.on('viewreset', this._redraw, this)
    map.on('mousemove', this._onMouseMove, this)
    map.on('mouseout', this._hideTooltip, this)

    this._redraw()
  },

  onRemove(this: any, map: L.Map) {
    this._hideTooltip()
    map.off('moveend', this._redraw, this)
    map.off('zoomend', this._redraw, this)
    map.off('resize', this._redraw, this)
    map.off('viewreset', this._redraw, this)
    map.off('mousemove', this._onMouseMove, this)
    map.off('mouseout', this._hideTooltip, this)
    if (this._canvas?.parentNode) {
      this._canvas.parentNode.removeChild(this._canvas)
    }
  },

  _hideTooltip(this: any) {
    if (this._tooltip && this._map) {
      this._map.closeTooltip(this._tooltip)
      this._tooltip = null
      this._hoverKey = null
    }
  },

  _cellsInView(this: any): RiskGridCell[] {
    const map: L.Map = this._map
    const bounds = map.getBounds().pad(0.05)
    const zoom = map.getZoom()
    const half = this.options.halfDeg as number
    const full = zoom >= (this.options.minZoomFull as number)

    // 低缩放抽稀：按粗网格桶取最大损失
    const bucketDeg = full ? 0 : Math.max(half * 2, 0.02 * Math.pow(2, 9 - zoom))
    const buckets = full ? null : new Map<string, RiskGridCell>()

    const out: RiskGridCell[] = []
    for (const cell of this._cells as RiskGridCell[]) {
      if (!bounds.contains([cell.lat, cell.lng])) continue
      if (!buckets) {
        out.push(cell)
        continue
      }
      const key = `${Math.round(cell.lat / bucketDeg)}_${Math.round(cell.lng / bucketDeg)}`
      const prev = buckets.get(key)
      if (!prev || cell.lossJpy > prev.lossJpy) buckets.set(key, cell)
    }
    if (buckets) return [...buckets.values()]
    return out
  },

  _redraw(this: any) {
    const map: L.Map = this._map
    if (!map || !this._canvas || !this._ctx) return

    const size = map.getSize()
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const canvas: HTMLCanvasElement = this._canvas
    canvas.width = Math.round(size.x * dpr)
    canvas.height = Math.round(size.y * dpr)
    canvas.style.width = `${size.x}px`
    canvas.style.height = `${size.y}px`

    const topLeft = map.containerPointToLayerPoint([0, 0])
    L.DomUtil.setPosition(canvas, topLeft)

    const ctx: CanvasRenderingContext2D = this._ctx
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, size.x, size.y)

    const half = this.options.halfDeg as number
    const maxLoss = this._maxLoss as number
    const cells = this._cellsInView()

    for (const cell of cells) {
      const t = Math.sqrt(Math.max(0, cell.lossJpy) / maxLoss)
      const sw = map.latLngToContainerPoint([cell.lat - half, cell.lng - half])
      const ne = map.latLngToContainerPoint([cell.lat + half, cell.lng + half])
      const x = Math.min(sw.x, ne.x)
      const y = Math.min(sw.y, ne.y)
      const w = Math.max(1, Math.abs(ne.x - sw.x))
      const h = Math.max(1, Math.abs(ne.y - sw.y))
      ctx.globalAlpha = 0.55 + t * 0.35
      ctx.fillStyle = lossColor(t)
      ctx.fillRect(x, y, w, h)
    }
    ctx.globalAlpha = 1
  },

  _onMouseMove(this: any, e: L.LeafletMouseEvent) {
    const map: L.Map = this._map
    const half = this.options.halfDeg as number
    const idxCell = this._indexCell as number
    const { lat, lng } = e.latlng
    const ix = Math.floor(lat / idxCell)
    const iy = Math.floor(lng / idxCell)

    let best: RiskGridCell | null = null
    let bestDist = Infinity
    const index = this._index as Map<string, RiskGridCell[]>

    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const bucket = index.get(`${ix + dx}_${iy + dy}`)
        if (!bucket) continue
        for (const cell of bucket) {
          const dLat = Math.abs(cell.lat - lat)
          const dLng = Math.abs(cell.lng - lng)
          if (dLat > half || dLng > half) continue
          const d = dLat * dLat + dLng * dLng
          if (d < bestDist) {
            bestDist = d
            best = cell
          }
        }
      }
    }

    if (!best) {
      this._hideTooltip()
      return
    }

    const key = `${best.lat},${best.lng}`
    if (this._hoverKey === key && this._tooltip) {
      this._tooltip.setLatLng(e.latlng)
      return
    }

    this._hideTooltip()
    this._hoverKey = key
    this._tooltip = L.tooltip({
      sticky: true,
      opacity: 1,
      className: 'muni-loss-tooltip-pane',
      direction: 'top',
      permanent: false,
    })
      .setContent(cellTooltipHtml(best))
      .setLatLng(e.latlng)
      .addTo(map)
  },
})

/** 按网格中心着色显示 Coupled_Loss_with_Other_JPY（单 Canvas） */
export function addGridLossLayer(
  cells: RiskGridCell[],
  layer: L.LayerGroup,
  halfDeg = 0.0041666667,
): [number, number][] {
  if (!cells.length) return []

  const canvasLayer = new (GridLossCanvas as any)(cells, { halfDeg, minZoomFull: 9 })
  layer.addLayer(canvasLayer)

  // 采样边界点用于 fitBounds（避免 3 万点）
  const bounds: [number, number][] = []
  const step = Math.max(1, Math.floor(cells.length / 400))
  for (let i = 0; i < cells.length; i += step) {
    const c = cells[i]!
    bounds.push([c.lat, c.lng])
  }
  const first = cells[0]!
  const last = cells[cells.length - 1]!
  bounds.push([first.lat, first.lng], [last.lat, last.lng])

  return bounds
}
