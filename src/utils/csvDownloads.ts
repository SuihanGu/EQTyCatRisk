import type { CouplingCatalogItem } from '../types'

function csvCell(value: unknown): string {
  const text = value == null ? '' : String(value)
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function downloadCsv(filename: string, headers: string[], rows: unknown[][]): void {
  const csv = '\uFEFF' + [headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function eligible(events: CouplingCatalogItem[]): CouplingCatalogItem[] {
  return events
    .filter((event) => event.couplingType?.toLowerCase() === 'simultaneous')
    .filter((event) => event.distanceKm == null || event.r30Km == null || event.distanceKm <= event.r30Km)
}

export function downloadCouplingMomentCsv(events: CouplingCatalogItem[]): void {
  const headers = [
    'z_id', 'coupling_type', 'eq_time', 'eq_lat', 'eq_lon', 'Mj', 'depth_km',
    'tc_time', 'tc_lat', 'tc_lon', 'wind_ms', 'dt_hours', 'distance_km', 'R30_km',
  ]
  const rows = eligible(events).map((event) => [
    event.id, 'Simultaneous', event.eqTime, event.epicenter.lat, event.epicenter.lng,
    event.magnitude, event.depthKm ?? '', event.tcTime, event.typhoonAtCoupling?.lat ?? '',
    event.typhoonAtCoupling?.lng ?? '', event.windMs, event.dtHours ?? '', event.distanceKm ?? '',
    event.r30Km ?? '',
  ])
  downloadCsv('Coupling moment information.csv', headers, rows)
}

export function downloadCompleteTyphoonTracksCsv(events: CouplingCatalogItem[]): void {
  const rows: unknown[][] = []
  eligible(events).forEach((event) => {
    event.typhoonPath.forEach((point) => {
      rows.push([event.id, 'Simultaneous', point.time ?? '', point.lat, point.lng, point.windMs ?? ''])
    })
  })
  downloadCsv('Complete set of typhoon events satisfying coupling conditions.csv',
    ['z_id', 'coupling_type', 'times', 'lats', 'lons', 'winds'], rows)
}

export function downloadLossCsv(filename: string, values: number[]): void {
  downloadCsv(filename, ['loss_oku'], values.map((value) => [value]))
}
