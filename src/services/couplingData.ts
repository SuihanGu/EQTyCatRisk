import type { CouplingCatalogFile, CouplingCatalogItem } from '../types'

let catalogCache: CouplingCatalogItem[] | null = null
let loadPromise: Promise<CouplingCatalogItem[]> | null = null

export async function loadCouplingCatalog(): Promise<CouplingCatalogItem[]> {
  if (catalogCache) return catalogCache
  if (loadPromise) return loadPromise

  loadPromise = (async () => {
    const res = await fetch('/data/coupling-events.json')
    if (!res.ok) {
      throw new Error(`Failed to load coupling events: ${res.status}`)
    }
    const data = (await res.json()) as CouplingCatalogFile
    catalogCache = data.events ?? []
    return catalogCache
  })()

  try {
    return await loadPromise
  } catch (err) {
    loadPromise = null
    throw err
  }
}

export function getCatalogSync(): CouplingCatalogItem[] {
  return catalogCache ?? []
}
