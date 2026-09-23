import type { RiskCaseEvent, RiskCaseFile, RiskGridCell } from '../types'

let cache: RiskCaseEvent | null = null
let loadPromise: Promise<RiskCaseEvent> | null = null
const gridPromises = new Map<string, Promise<RiskGridCell[]>>()

type CompactCell = [
  number, // lat
  number, // lng
  number, // lossJpy
  string | undefined, // name
  number | undefined, // population
  number | null | undefined, // pga
  number | null | undefined, // wind
]

type GridFile = {
  version: number
  halfDeg?: number
  cells: CompactCell[] | RiskGridCell[]
}

function normalizeGridCells(raw: CompactCell[] | RiskGridCell[]): RiskGridCell[] {
  if (!raw.length) return []
  const first = raw[0]
  if (Array.isArray(first)) {
    return (raw as CompactCell[]).map((row) => {
      const cell: RiskGridCell = {
        lat: row[0],
        lng: row[1],
        lossJpy: row[2],
      }
      if (row[3]) cell.name = row[3]
      if (row[4] != null) cell.population = row[4]
      if (row[5] != null) cell.pgaGal = row[5]
      if (row[6] != null) cell.windMs = row[6]
      return cell
    })
  }
  return raw as RiskGridCell[]
}

function normalizeRiskEvent(event: RiskCaseEvent): RiskCaseEvent {
  event.lossByPrefecture = event.lossByRegion ?? {}
  event.windMs = event.windMs ?? 0
  event.windSpeed = event.windSpeed ?? event.windMs * 3.6
  event.gridCells = event.gridCells ?? []
  return event
}

export async function loadRiskCases(): Promise<RiskCaseEvent[]> {
  const res = await fetch('/data/risk-cases.json')
  if (!res.ok) throw new Error(`Failed to load risk cases: ${res.status}`)
  const data = await res.json() as RiskCaseFile & { cases?: RiskCaseEvent[] }
  return (data.cases ?? (data.event ? [data.event] : [])).map(normalizeRiskEvent)
}

/** 仅加载算例元数据（地图可先出台风/震源） */
export async function loadRiskCase(): Promise<RiskCaseEvent> {
  if (cache) return cache
  if (loadPromise) return loadPromise

  loadPromise = (async () => {
    const event = (await loadRiskCases())[0]
    if (!event) throw new Error('Risk case catalogue is empty')
    cache = event
    return cache
  })()

  try {
    return await loadPromise
  } catch (err) {
    loadPromise = null
    throw err
  }
}

/** 异步加载紧凑网格损失（JPY） */
export async function loadRiskGridCells(event?: RiskCaseEvent | null): Promise<RiskGridCell[]> {
  if (event?.gridCells?.length) return event.gridCells
  if (cache?.gridCells?.length && (!event || cache.id === event.id)) return cache.gridCells
  const url =
    (event as RiskCaseEvent & { gridCellsUrl?: string } | null | undefined)?.gridCellsUrl ||
    (cache as RiskCaseEvent & { gridCellsUrl?: string } | null)?.gridCellsUrl ||
    '/data/risk-grid-cells-2005.json'

  const existing = gridPromises.get(url)
  if (existing) return existing
  const promise = (async () => {
    const res = await fetch(url)
    if (!res.ok) {
      throw new Error(`Failed to load grid loss data: ${res.status}`)
    }
    const data = (await res.json()) as GridFile
    const cells = normalizeGridCells(data.cells)
    if (cache && cache.id === event?.id) {
      cache = {
        ...cache,
        gridCells: cells,
        gridHalfDeg: data.halfDeg ?? cache.gridHalfDeg,
      }
    }
    return cells
  })()
  gridPromises.set(url, promise)

  try {
    return await promise
  } catch (err) {
    gridPromises.delete(url)
    throw err
  }
}
