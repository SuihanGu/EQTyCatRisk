/** 统一耦合类型展示：禁止 EQ-TY / TY-EQ 缩写 */
export function formatCouplingType(raw?: string | null): string {
  if (!raw) return '—'
  const key = raw.trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')
  const map: Record<string, string> = {
    'eq ty': 'Earthquake followed by Typhoon',
    'ty eq': 'Typhoon followed by Earthquake',
    'earthquake followed by typhoon': 'Earthquake followed by Typhoon',
    'typhoon followed by earthquake': 'Typhoon followed by Earthquake',
    simultaneous: 'Simultaneous',
  }
  return map[key] ?? raw.trim()
}

export function formatJpy(value: number): string {
  if (!Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)}e8 JPY`
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)} M JPY`
  return `${Math.round(value).toLocaleString('en-US')} JPY`
}
