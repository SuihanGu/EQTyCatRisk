import type { FeatureCollection } from 'geojson'

let cache: FeatureCollection | null = null
let loadPromise: Promise<FeatureCollection> | null = null

export async function loadMunicipalityGeoJson(): Promise<FeatureCollection> {
  if (cache) return cache
  if (loadPromise) return loadPromise

  loadPromise = (async () => {
    const res = await fetch('/data/hokkaido-municipalities.geojson')
    if (!res.ok) throw new Error(`Failed to load municipality boundaries: ${res.status}`)
    cache = (await res.json()) as FeatureCollection
    return cache
  })()

  try {
    return await loadPromise
  } catch (err) {
    loadPromise = null
    throw err
  }
}
