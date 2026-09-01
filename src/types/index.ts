export interface TyphoonPoint {
  lat: number
  lng: number
  windMs?: number
  /** 路径点时刻（UTC ISO），来自完整台风事件集 times */
  time?: string
}

export interface CouplingEvent {
  id: string
  magnitude: number
  /** 耦合时刻风速，km/h（由 wind_ms 换算，便于展示） */
  windSpeed: number
  /** 耦合时刻风速，m/s（原始字段 wind_ms） */
  windMs: number
  year: number
  epicenter: TyphoonPoint
  typhoonPath: TyphoonPoint[]
  descriptions: string[]
  lossByPrefecture: Record<string, number>
  structureLoss: {
    wood: number
    steel: number
    rc: number
    masonry: number
  }
  /** 以下字段来自 data/第一页的数据 */
  basin?: string
  couplingType?: string
  /** 震源深度 km */
  depthKm?: number | null
  pressureHpa?: number | null
  dtHours?: number | null
  distanceKm?: number | null
  r34Km?: number | null
  eqTime?: string
  tcTime?: string
  typhoonAtCoupling?: TyphoonPoint | null
  typhoonWinds?: number[]
  sourceIndex?: number
}

export interface CouplingCatalogItem {
  id: string
  basin: string | null
  couplingType: string | null
  magnitude: number
  depthKm?: number | null
  windMs: number
  windSpeed: number
  pressureHpa: number | null
  dtHours: number | null
  distanceKm: number | null
  r34Km: number | null
  eqTime: string
  tcTime: string
  year?: number | null
  epicenter: TyphoonPoint
  typhoonAtCoupling: TyphoonPoint | null
  typhoonPath: TyphoonPoint[]
  typhoonWinds: number[]
  index: number
}

export interface CouplingCatalogFile {
  version: number
  count: number
  events: CouplingCatalogItem[]
}

export interface Prefecture {
  id: string
  name: string
  lat: number
  lng: number
}

/** 第二页风险算例：市町村暴露聚合 */
export interface RiskRegion {
  id: string
  name: string
  population: number
  meanPgaGal: number
  meanWindMs: number
  /** 兼容旧字段：等同 lossJpy（整数） */
  lossIndex: number
  /** 耦合损失，JPY */
  lossJpy?: number
  lat?: number | null
  lng?: number | null
}

/** 第二页网格损失点（Coupled_Loss_with_Other_JPY） */
export interface RiskGridCell {
  lat: number
  lng: number
  lossJpy: number
  population?: number
  name?: string
  pgaGal?: number
  windMs?: number
}

export interface RiskCaseEvent extends CouplingEvent {
  label: string
  depthKm?: number
  typhoonCode?: string
  typhoonName?: string
  regions: RiskRegion[]
  /** 有损网格（中心点 + JPY） */
  gridCells?: RiskGridCell[]
  gridHalfDeg?: number
  /** 分文件加载网格 */
  gridCellsUrl?: string
  totalCoupledLossJpy?: number
  lossByRegion: Record<string, number>
}

export interface RiskCaseFile {
  version: number
  event: RiskCaseEvent
}
