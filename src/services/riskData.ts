import type { RiskCaseEvent, RiskCaseFile, RiskGridCell } from '../types'

let cache: RiskCaseEvent | null = null
let loadPromise: Promise<RiskCaseEvent> | null = null
let gridPromise: Promise<RiskGridCell[]> | null = null

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

/** 仅加载算例元数据（地图可先出台风/震源） */
export async function loadRiskCase(): Promise<RiskCaseEvent> {
  if (cache) return cache
  if (loadPromise) return loadPromise

  loadPromise = (async () => {
    const res = await fetch('/data/risk-iburi-jebi.json')
    if (!res.ok) {
      throw new Error(`Failed to load risk case: ${res.status}`)
    }
    const data = (await res.json()) as RiskCaseFile & {
      event: RiskCaseEvent & { gridCellsUrl?: string }
    }
    const event = data.event
    event.lossByPrefecture = event.lossByRegion ?? {}
    event.windMs = event.windMs ?? 0
    event.windSpeed = event.windSpeed ?? event.windMs * 3.6
    event.gridCells = event.gridCells ?? []
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
  if (cache?.gridCells?.length) return cache.gridCells
  if (gridPromise) return gridPromise

  const url =
    (event as RiskCaseEvent & { gridCellsUrl?: string } | null | undefined)?.gridCellsUrl ||
    (cache as RiskCaseEvent & { gridCellsUrl?: string } | null)?.gridCellsUrl ||
    '/data/risk-grid-cells.json'

  gridPromise = (async () => {
    const res = await fetch(url)
    if (!res.ok) {
      throw new Error(`Failed to load grid loss data: ${res.status}`)
    }
    const data = (await res.json()) as GridFile
    const cells = normalizeGridCells(data.cells)
    if (cache) {
      cache = {
        ...cache,
        gridCells: cells,
        gridHalfDeg: data.halfDeg ?? cache.gridHalfDeg,
      }
    }
    return cells
  })()

  try {
    return await gridPromise
  } catch (err) {
    gridPromise = null
    throw err
  }
}
