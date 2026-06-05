/**
 * 第一層 · 魚場潛勢精準化（自帶型別的純函式模組，不依賴 @/data，零耦合）。
 *
 * 與同學分工：同學的 nowMath.suit() 負責「每格環境適合度」(SST/鋒面/海流/季節/趨勢，加權相加)。
 * 本模組「不重算」環境適合度，而是吃他的 suit 輸出，再補上他沒有的兩件事，把熱區收緊到貼近真實：
 *   1. 該魚種同季「歷史出現密度(KDE)」——魚真的會出現的地方
 *   2. 信心門檻 + 自適應百分位 + 侵蝕「取核心」——取代固定 HOT_THR=70 的大塊熱區
 *
 * 為何用「相乘 gate」而非他的「相加」：相加時暖水單項就能撐高分、熱區收不緊；
 * 把出現密度/信心以相乘包在他的 suit 外面，才會「環境合適 且 歷史會出現」兩者同時成立才亮。
 *
 * 接線方式（待 data 層穩定後，由 nowLayers/useDeckLayers 接；本檔不主動接線）：
 *   const envSuit = grid.map(c => suit(c.v, sp, month, { front: c.front, u: c.u, w: c.w, trend: c.trend })) // 同學的 suit(0–100)
 *   const dens    = occurrenceDensity(grid, occ, sp.name, month)
 *   const score   = fishScore(envSuit, dens)            // 環境 × 歷史出現 → 0–1
 *   const conf    = confidenceFromOccurrence(grid, occ, sp.name, month)
 *   const cores   = extractCores(score, conf, grid, step)
 * 另：若現在頁網格尚無鋒面欄位，frontFactor(grid, step) 可當同學 suit 的 env.front 供應者(反向幫到他)。
 *
 * 誠實定位：輸出為「該魚種出現潛勢」，非漁獲量(無 CPUE)。
 */

// --- 自帶型別（自含、不 import @/data）--------------------------------------
export interface GeoCell {
  lat: number
  lon: number
  v?: number | null // SST(現在頁為浮標 IDW 內插)
  u?: number // 海流東向分量
  w?: number // 海流北向分量
}

export interface OccPoint {
  lat: number
  lon: number
  month: number
  species: string
}

export interface HotCore {
  cellIdx: number[] // 屬於此核心的 cells 索引
  peak: number // 核心內最高魚場分數 0–1
  areaKm2: number
  centroid: [number, number] // [lon, lat]
  drift: { deg: number; spd: number; dir: string } | null // 聚合海流方向
}

export interface CoreOptions {
  topPct?: number // 取分數前段比例(預設 0.12)
  confMin?: number // 信心門檻(預設 0.3)
  minSize?: number // 核心最小格數(預設 2)
  erode?: boolean // 是否侵蝕去邊緣一格(預設 true)
}

export interface ScoreOptions {
  suitMax?: number // 同學 suit 的上限(預設 100，換算成 0–1)
  densityExp?: number // 出現密度的指數(>1 更嚴格收緊；預設 1)
  densityFloor?: number // 無出現點處仍給的底，避免全黑(預設 0.15)
}

const DEG_KM = 111.32
const DIR8 = ['北', '東北', '東', '東南', '南', '西南', '西', '西北']

// 等距近似(度)：經度依緯度做 cos 修正，足夠 KDE / 鄰接判斷使用。
function distDeg(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const k = Math.cos((((aLat + bLat) / 2) * Math.PI) / 180)
  const dx = (aLon - bLon) * k
  const dy = aLat - bLat
  return Math.hypot(dx, dy)
}

function normalize(arr: (number | null)[]): number[] {
  let max = 0
  for (const v of arr) if (v != null && v > max) max = v
  return arr.map((v) => (v == null || max <= 0 ? 0 : v / max))
}

const monthDiff = (a: number, b: number): number => {
  const d = Math.abs(a - b) % 12
  return Math.min(d, 12 - d) // 循環(12 月與 1 月相差 1)
}

/**
 * 該魚種出現點的高斯核密度(KDE)，標準化為每格 0–1。
 * 月份採「柔性權重」(高斯，monthSigma)：當月附近權重最高，但**不硬切**——
 * 避免「蘭嶼飛魚記錄在 2–5 月、6 月查不到」這類季前/季尾被整個濾掉的問題。
 */
export function occurrenceDensity(
  cells: GeoCell[],
  occ: OccPoint[],
  species: string,
  month: number,
  opts: { monthSigma?: number; bandwidthDeg?: number } = {},
): number[] {
  const mSigma = opts.monthSigma ?? 2 // 月份權重高斯寬度(月)
  const bw = opts.bandwidthDeg ?? 0.25
  const pts = occ.filter((o) => o.species === species)
  if (!pts.length) return cells.map(() => 0)
  const inv2bw2 = 1 / (2 * bw * bw)
  const inv2m2 = 1 / (2 * mSigma * mSigma)
  // 預先算各點的月份權重，<0.05 直接略過(離當季太遠)
  const wm = pts.map((p) => Math.exp(-(monthDiff(p.month, month) ** 2) * inv2m2))
  const raw = cells.map((c) => {
    let sum = 0
    for (let k = 0; k < pts.length; k++) {
      if (wm[k] < 0.05) continue
      const d = distDeg(c.lat, c.lon, pts[k].lat, pts[k].lon)
      if (d <= 3 * bw) sum += wm[k] * Math.exp(-(d * d) * inv2bw2)
    }
    return sum
  })
  return normalize(raw)
}

/**
 * 信心 0–1：每格到最近「該魚種(任何月份)出現點」的距離 → exp(-(d/scale)^2)。
 * 月份無關：只要該魚種曾在此海域出現過就有資料支持(避免把蘭嶼這類有記錄但非當月的海域當低信心)。
 */
export function confidenceFromOccurrence(
  cells: GeoCell[],
  occ: OccPoint[],
  species: string,
  _month: number,
  opts: { scaleDeg?: number } = {},
): number[] {
  const scale = opts.scaleDeg ?? 0.3
  const pts = occ.filter((o) => o.species === species)
  if (!pts.length) return cells.map(() => 0)
  return cells.map((c) => {
    let near = Infinity
    for (const p of pts) {
      const d = distDeg(c.lat, c.lon, p.lat, p.lon)
      if (d < near) near = d
    }
    return Math.exp(-((near / scale) ** 2))
  })
}

/**
 * 鋒面因子 0–1：以鄰格 SST 差分估 |∇SST| 並標準化。
 * 本模組的魚場分數「不」再用它(鋒面已含在同學 suit)；保留此函式是給現在頁網格
 * 若缺鋒面欄位時，當同學 suit 的 env.front 供應者(反向支援)。
 */
export function frontFactor(cells: GeoCell[], step: number): number[] {
  const key = (lat: number, lon: number): string =>
    `${Math.round(lat / step)}|${Math.round(lon / step)}`
  const byKey = new Map<string, number>()
  cells.forEach((c, i) => byKey.set(key(c.lat, c.lon), i))
  const grad = cells.map((c) => {
    if (c.v == null) return null
    const e = byKey.get(key(c.lat, c.lon + step))
    const wst = byKey.get(key(c.lat, c.lon - step))
    const n = byKey.get(key(c.lat + step, c.lon))
    const s = byKey.get(key(c.lat - step, c.lon))
    const gx = diff(cells, e, wst, c.v)
    const gy = diff(cells, n, s, c.v)
    return Math.hypot(gx, gy)
  })
  return normalize(grad)
}

function diff(
  cells: GeoCell[],
  hi: number | undefined,
  lo: number | undefined,
  center: number,
): number {
  const a = hi != null && cells[hi].v != null ? (cells[hi].v as number) : center
  const b = lo != null && cells[lo].v != null ? (cells[lo].v as number) : center
  return (a - b) / 2
}

/**
 * 魚場分數 = 同學環境適合度(envSuit) × 歷史出現密度(gate)，標準化 0–1。
 * 相乘(而非相加)：唯有「環境合適」且「歷史會出現」兩者同時成立才高分 → 熱區自然收緊、貼近真實漁場。
 * densityFloor 保留無出現點處的微弱底色，避免整圖全黑；但因低於門檻不會形成核心。
 */
export function fishScore(
  envSuit: (number | null)[],
  density: number[],
  opts: ScoreOptions = {},
): number[] {
  const suitMax = opts.suitMax ?? 100
  const exp = opts.densityExp ?? 1
  const floor = opts.densityFloor ?? 0.15
  const raw = envSuit.map((s, i) => {
    if (s == null || s <= 0) return 0
    const env = Math.max(0, Math.min(1, s / suitMax))
    const dens = floor + (1 - floor) * Math.pow(Math.max(0, density[i] ?? 0), exp)
    return env * dens
  })
  return normalize(raw)
}

/**
 * 取核心熱區：score 前 topPct 且 conf≥confMin → 4 鄰接連通分群 →(可選)侵蝕去邊緣一格
 * → 只留 size≥minSize 的群。用相對百分位取代固定門檻 70，使熱區小而集中。
 */
export function extractCores(
  scores: number[],
  conf: number[],
  cells: GeoCell[],
  step: number,
  opts: CoreOptions = {},
): HotCore[] {
  const topPct = opts.topPct ?? 0.12
  const confMin = opts.confMin ?? 0.3
  const minSize = opts.minSize ?? 2
  const erode = opts.erode ?? true

  const cand = scores
    .map((s, i) => ({ i, s }))
    .filter((o) => o.s > 0 && (conf[o.i] ?? 0) >= confMin)
  if (!cand.length) return []

  const sorted = [...cand].sort((a, b) => b.s - a.s)
  const cut = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * topPct))].s
  let keep = new Set(cand.filter((o) => o.s >= cut).map((o) => o.i))

  const key = (lat: number, lon: number): string =>
    `${Math.round(lat / step)}|${Math.round(lon / step)}`
  const idxByKey = new Map<string, number>()
  cells.forEach((c, i) => idxByKey.set(key(c.lat, c.lon), i))
  const nb = (i: number): number[] => {
    const c = cells[i]
    return [
      idxByKey.get(key(c.lat + step, c.lon)),
      idxByKey.get(key(c.lat - step, c.lon)),
      idxByKey.get(key(c.lat, c.lon + step)),
      idxByKey.get(key(c.lat, c.lon - step)),
    ].filter((x): x is number => x !== undefined)
  }

  if (erode && keep.size > minSize) {
    const eroded = new Set(
      [...keep].filter((i) => nb(i).filter((j) => keep.has(j)).length >= 2),
    )
    if (eroded.size >= minSize) keep = eroded
  }

  const seen = new Set<number>()
  const cores: HotCore[] = []
  for (const start of keep) {
    if (seen.has(start)) continue
    const stack = [start]
    const group: number[] = []
    seen.add(start)
    while (stack.length) {
      const cur = stack.pop() as number
      group.push(cur)
      for (const j of nb(cur)) {
        if (keep.has(j) && !seen.has(j)) {
          seen.add(j)
          stack.push(j)
        }
      }
    }
    if (group.length < minSize) continue
    cores.push(buildCore(group, scores, cells, step))
  }
  return cores.sort((a, b) => b.peak - a.peak)
}

function buildCore(
  group: number[],
  scores: number[],
  cells: GeoCell[],
  step: number,
): HotCore {
  let peak = 0
  let sumLat = 0
  let sumLon = 0
  let mu = 0
  let mw = 0
  let nUv = 0
  for (const i of group) {
    if (scores[i] > peak) peak = scores[i]
    sumLat += cells[i].lat
    sumLon += cells[i].lon
    if (cells[i].u !== undefined && cells[i].w !== undefined) {
      mu += cells[i].u as number
      mw += cells[i].w as number
      nUv++
    }
  }
  const centroid: [number, number] = [sumLon / group.length, sumLat / group.length]
  const latMean = sumLat / group.length
  const cellKm2 = (step * DEG_KM) ** 2 * Math.cos((latMean * Math.PI) / 180)
  let drift: HotCore['drift'] = null
  if (nUv > 0) {
    mu /= nUv
    mw /= nUv
    const spd = Math.hypot(mu, mw)
    const deg = ((Math.atan2(mu, mw) * 180) / Math.PI + 360) % 360
    drift = { deg, spd, dir: DIR8[Math.round(deg / 45) % 8] }
  }
  return { cellIdx: group, peak, areaKm2: group.length * cellKm2, centroid, drift }
}
