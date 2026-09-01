import { JAPAN_PREFECTURES } from '../data/prefectures'
import type { CouplingCatalogItem, CouplingEvent, TyphoonPoint } from '../types'
import { formatCouplingType } from './formatters'

/** 由事件 id 派生稳定伪随机，同一事件损失固定，避免每次“生成”抖动 */
function seededUnit(seed: string, salt: number): number {
  let h = (salt * 2654435761) >>> 0
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 16777619)
  }
  return ((h >>> 0) % 10000) / 10000
}

function seededBetween(seed: string, salt: number, min: number, max: number, digits = 1): number {
  const value = min + seededUnit(seed, salt) * (max - min)
  return Number(value.toFixed(digits))
}

function haversineKm(a: TyphoonPoint, b: TyphoonPoint): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const R = 6371
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const lat1 = toRad(a.lat)
  const lat2 = toRad(b.lat)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)))
}

function estimateLossByPrefecture(
  eventId: string,
  magnitude: number,
  windSpeed: number,
  epicenter: TyphoonPoint,
): Record<string, number> {
  const loss: Record<string, number> = {}
  const intensity = magnitude * 0.6 + windSpeed * 0.04

  JAPAN_PREFECTURES.forEach((pref, i) => {
    const dist = haversineKm(epicenter, pref)
    const atten = Math.max(0.25, 1 - dist / 1800)
    const base = intensity * seededBetween(eventId, i + 1, 8, 22) * atten
    loss[pref.id] = Math.round(base * seededBetween(eventId, i + 100, 0.75, 1.25))
  })

  return loss
}

function estimateStructureLoss(eventId: string, totalLoss: number) {
  const wood = Math.round(totalLoss * seededBetween(eventId, 501, 0.22, 0.34))
  const steel = Math.round(totalLoss * seededBetween(eventId, 502, 0.18, 0.28))
  const rc = Math.round(totalLoss * seededBetween(eventId, 503, 0.24, 0.36))
  const masonry = Math.max(0, totalLoss - wood - steel - rc)
  return { wood, steel, rc, masonry }
}

function yearFromItem(item: CouplingCatalogItem): number {
  if (item.year != null && Number.isFinite(item.year)) return item.year
  const y = Number(item.eqTime?.slice(0, 4))
  return Number.isFinite(y) ? y : item.index + 1
}

function buildDescriptions(item: CouplingCatalogItem): string[] {
  const lines: string[] = [
    `Event ${item.id}`,
    `Coupling type ${formatCouplingType(item.couplingType)}`,
    `Epicenter ${item.epicenter.lat.toFixed(2)}°N, ${item.epicenter.lng.toFixed(2)}°E, Mw ${item.magnitude.toFixed(2)}`,
  ]
  if (item.depthKm != null) {
    lines.push(`Focal depth ${item.depthKm.toFixed(1)} km`)
  }
  lines.push(
    `Typhoon wind at coupling ${item.windMs.toFixed(1)} m/s (≈ ${item.windSpeed.toFixed(0)} km/h)`,
  )

  if (item.eqTime) lines.push(`Earthquake time (UTC) ${item.eqTime}`)
  if (item.tcTime) lines.push(`Typhoon coupling time (UTC) ${item.tcTime}`)
  if (item.distanceKm != null) {
    lines.push(`Epicenter–typhoon distance ≈ ${item.distanceKm.toFixed(1)} km`)
  }
  if (item.r34Km != null) {
    lines.push(`R34 ≈ ${item.r34Km.toFixed(1)} km`)
  }
  if (item.dtHours != null) {
    lines.push(
      `dt_hours = ${item.dtHours.toFixed(1)} h (positive: typhoon first; negative: earthquake first)`,
    )
  }
  if (item.typhoonPath.length) {
    lines.push(`Full typhoon track: ${item.typhoonPath.length} points`)
  }

  return lines
}

/** 地图绘制用轻量对象，不估算损失 */
export function catalogItemToMapEvent(item: CouplingCatalogItem): CouplingEvent {
  return {
    id: item.id,
    magnitude: item.magnitude,
    windSpeed: item.windSpeed,
    windMs: item.windMs,
    year: yearFromItem(item),
    epicenter: item.epicenter,
    typhoonPath: item.typhoonPath,
    descriptions: [],
    lossByPrefecture: {},
    structureLoss: { wood: 0, steel: 0, rc: 0, masonry: 0 },
    basin: item.basin ?? undefined,
    couplingType: formatCouplingType(item.couplingType),
    depthKm: item.depthKm ?? undefined,
    pressureHpa: item.pressureHpa,
    dtHours: item.dtHours,
    distanceKm: item.distanceKm,
    r34Km: item.r34Km,
    eqTime: item.eqTime,
    tcTime: item.tcTime,
    typhoonAtCoupling: item.typhoonAtCoupling,
    typhoonWinds: item.typhoonWinds,
    sourceIndex: item.index,
  }
}

/** 将目录中的真实耦合事件转为前端 CouplingEvent（损失为基于强度的稳定估算） */
export function catalogItemToEvent(item: CouplingCatalogItem): CouplingEvent {
  const lossByPrefecture = estimateLossByPrefecture(
    item.id,
    item.magnitude,
    item.windSpeed,
    item.epicenter,
  )
  const totalLoss = Object.values(lossByPrefecture).reduce((sum, v) => sum + v, 0)

  return {
    id: item.id,
    magnitude: item.magnitude,
    windSpeed: item.windSpeed,
    windMs: item.windMs,
    year: yearFromItem(item),
    epicenter: item.epicenter,
    typhoonPath: item.typhoonPath,
    descriptions: buildDescriptions(item),
    lossByPrefecture,
    structureLoss: estimateStructureLoss(item.id, totalLoss),
    basin: item.basin ?? undefined,
    couplingType: formatCouplingType(item.couplingType),
    depthKm: item.depthKm ?? undefined,
    pressureHpa: item.pressureHpa,
    dtHours: item.dtHours,
    distanceKm: item.distanceKm,
    r34Km: item.r34Km,
    eqTime: item.eqTime,
    tcTime: item.tcTime,
    typhoonAtCoupling: item.typhoonAtCoupling,
    typhoonWinds: item.typhoonWinds,
    sourceIndex: item.index,
  }
}

