import { formatCouplingType } from './formatters'

/** 从 z_id（EQ-…__TC-TY2407）解析台风编号 */
export function typhoonCodeFromZid(zid: string): string {
  if (!zid.includes('__TC-')) return zid
  return zid.split('__TC-')[1] ?? zid
}

/** 从 z_id 解析地震侧短标签 */
export function earthquakeLabelFromZid(zid: string): string {
  if (!zid.includes('__TC-')) return zid
  const eq = zid.split('__TC-')[0] ?? zid
  return eq.replace(/^EQ-/, 'EQ')
}

export function pairHoverHtml(opts: {
  zid: string
  magnitude: number
  couplingType?: string | null
  eqTime?: string
  tcTime?: string
  windMs?: number
  lat: number
  lng: number
}): string {
  const tc = typhoonCodeFromZid(opts.zid)
  const type = formatCouplingType(opts.couplingType)
  const year = opts.eqTime?.slice(0, 4) || '—'
  const wind =
    opts.windMs != null && Number.isFinite(opts.windMs)
      ? `${opts.windMs.toFixed(1)} m/s`
      : '—'

  return `
    <div class="pair-tooltip">
      <div class="pair-tooltip-title">Coupling event</div>
      <div class="pair-tooltip-row"><span>Earthquake</span><strong>Mw ${opts.magnitude.toFixed(2)}</strong></div>
      <div class="pair-tooltip-row"><span>Typhoon</span><strong>${tc}</strong></div>
      <div class="pair-tooltip-row"><span>Type</span><strong>${type}</strong></div>
      <div class="pair-tooltip-row"><span>Year</span><strong>${year}</strong></div>
      <div class="pair-tooltip-row"><span>Wind</span><strong>${wind}</strong></div>
      <div class="pair-tooltip-coord">${opts.lat.toFixed(2)}°N · ${opts.lng.toFixed(2)}°E</div>
    </div>
  `
}
