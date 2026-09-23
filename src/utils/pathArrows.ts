import L from 'leaflet'

/** 地理方位角：从 a 指向 b（度，顺时针自北） */
export function bearingDeg(a: [number, number], b: [number, number]): number {
  const lat1 = (a[0] * Math.PI) / 180
  const lat2 = (b[0] * Math.PI) / 180
  const dLng = ((b[1] - a[1]) * Math.PI) / 180
  const y = Math.sin(dLng) * Math.cos(lat2)
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng)
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
}

function midpoint(a: [number, number], b: [number, number]): [number, number] {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
}

function createArrowIcon(color: string, bearing: number, size: number): L.DivIcon {
  const half = size / 2
  // SVG 箭头：白描边 + 实心填充，对比更强
  const svg = `
    <svg class="typhoon-arrow-svg" width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true"
      style="transform:rotate(${bearing}deg)">
      <path d="M12 3 L20 17 L12 13.5 L4 17 Z"
        fill="${color}"
        stroke="#ffffff"
        stroke-width="2.2"
        stroke-linejoin="round"
        paint-order="stroke fill"/>
    </svg>`
  return L.divIcon({
    className: 'typhoon-arrow-wrap',
    html: svg,
    iconSize: [size, size],
    iconAnchor: [half, half],
  })
}

export type PathArrowOptions = {
  color: string
  /** 约每隔多少段放一个箭头 */
  every?: number
  /** 最多箭头数 */
  maxArrows?: number
  size?: number
  opacity?: number
  interactive?: boolean
}

/**
 * 沿折线放置方向箭头：从时间早（起点）指向时间近（终点）。
 * coords 须按时间升序。
 */
export function addPathDirectionArrows(
  coords: [number, number][],
  layer: L.LayerGroup,
  options: PathArrowOptions,
): void {
  if (coords.length < 2) return

  const every = Math.max(1, options.every ?? 3)
  const maxArrows = options.maxArrows ?? 16
  const size = options.size ?? 18
  const opacity = options.opacity ?? 1
  const interactive = options.interactive ?? false

  const candidates: number[] = []
  for (let i = 0; i < coords.length - 1; i += every) {
    candidates.push(i)
  }
  // 保证接近终点处也有箭头
  const lastSeg = coords.length - 2
  if (!candidates.includes(lastSeg)) candidates.push(lastSeg)

  const step = Math.max(1, Math.ceil(candidates.length / maxArrows))
  const picked = candidates.filter((_, idx) => idx % step === 0)

  picked.forEach((i) => {
    const a = coords[i]!
    const b = coords[i + 1]!
    if (a[0] === b[0] && a[1] === b[1]) return

    const bearing = bearingDeg(a, b)
    const mid = midpoint(a, b)
    L.marker(mid, {
      icon: createArrowIcon(options.color, bearing, size),
      interactive,
      keyboard: false,
      zIndexOffset: 650,
      opacity,
    }).addTo(layer)
  })
}
