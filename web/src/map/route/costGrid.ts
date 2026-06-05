/**
 * 第二層 · 航線規劃：成本場(cost grid)建構（自帶型別純函式，零耦合）。
 *
 * 把各圖層組成每格「通行成本」，供 A*(astar.ts) 搜尋最低成本航線。
 * 輸入多已存在於專案：魚場分數(第一層)、波高(浮標)、海流(現在頁)、信心、陸地遮罩。
 *
 * objective 權重組合（成本越低越優先）：
 *   fish  最高魚場  —— 魚場分數高→成本低為主
 *   short 最短距離  —— 幾乎只看距離
 *   safe  最安全    —— 強烈避開高浪/強逆流
 *   fuel  低油耗    —— 距離 + 逆流加成
 * 陸地 / 範圍外格為不可通行(Infinity)。
 */

export interface RouteCell {
  lat: number
  lon: number
  score?: number | null // 0–1 魚場分數(第一層)
  wave?: number | null // 示性波高 m
  u?: number // 海流東向 m/s
  w?: number // 海流北向 m/s
  conf?: number | null // 0–1 信心
  land?: boolean // 陸地/不可通行
}

export type Objective = 'fish' | 'short' | 'safe' | 'fuel'

export interface CostWeights {
  dist: number // 基礎距離成本(每格)
  fish: number // 魚場分數降低成本的權重
  wave: number // 波高提高成本的權重
  conf: number // 低信心加罰
}

export const OBJECTIVE_WEIGHTS: Record<Objective, CostWeights> = {
  fish: { dist: 1, fish: 2.5, wave: 1.0, conf: 0.8 },
  short: { dist: 1, fish: 0.2, wave: 0.3, conf: 0.1 },
  safe: { dist: 1, fish: 0.5, wave: 4.0, conf: 0.5 },
  fuel: { dist: 1.5, fish: 0.5, wave: 1.5, conf: 0.3 },
}

const WAVE_REF = 4.0 // m，波高正規化參考(>=此值視為高浪)

/**
 * 建每格「節點成本」(>=0；陸地/範圍外=Infinity)。
 * 注意：這是「停留在該格的成本」，A* 的邊成本另以距離×平均節點成本計。
 */
export function buildCostField(
  cells: RouteCell[],
  objective: Objective = 'fish',
  weightsOverride?: Partial<CostWeights>,
): number[] {
  const w = { ...OBJECTIVE_WEIGHTS[objective], ...weightsOverride }
  return cells.map((c) => {
    if (c.land) return Infinity
    const score = c.score == null ? 0 : Math.max(0, Math.min(1, c.score))
    const waveN = c.wave == null ? 0 : Math.max(0, Math.min(1, c.wave / WAVE_REF))
    const conf = c.conf == null ? 1 : Math.max(0, Math.min(1, c.conf))
    // 基礎 + 高浪加成 + 低信心加罰 − 魚場分數折扣；最後夾為正值
    const cost =
      w.dist + w.wave * waveN + w.conf * (1 - conf) - w.fish * score
    return Math.max(0.05, cost)
  })
}

/** 逆流加成(可選，fuel/ safe 用)：沿移動方向與海流相反時提高成本。回傳 0–1 加成係數。 */
export function againstCurrentFactor(
  cell: RouteCell,
  headingDeg: number,
): number {
  if (cell.u === undefined || cell.w === undefined) return 0
  const flowDeg = ((Math.atan2(cell.u, cell.w) * 180) / Math.PI + 360) % 360
  const diff = Math.abs(((headingDeg - flowDeg + 540) % 360) - 180) // 0=同向,180=逆向
  const spd = Math.hypot(cell.u, cell.w)
  return (diff / 180) * Math.min(1, spd / 1.5) // 逆向且流強→接近 1
}
