/**
 * 第二層 · 航線規劃：A* 最低成本路徑搜尋（自帶型別純函式，零耦合）。
 *
 * 在規則網格(0.05°)上以 8 鄰接搜尋從起點到目標的最低成本航線。
 * 邊成本 = 兩格距離(km) × 兩格節點成本平均(來自 costGrid.buildCostField)。
 * 啟發式 = 大圓距離 × 最小每公里成本(admissible，保證找到最佳解)。
 * 陸地/範圍外節點成本為 Infinity，自動繞開。
 *
 * 接線方式（待 data 層穩定後）：
 *   const cost = buildCostField(cells, objective)
 *   const res  = astar({ cells, step, cost, start, goal })
 *   把 res.path 餵給 deck.gl PathLayer 畫航線。
 */

export interface RoutePoint {
  lat: number
  lon: number
}

export interface AstarInput {
  cells: { lat: number; lon: number }[]
  step: number
  cost: number[] // 每格節點成本(Infinity=不可通行)，長度同 cells
  start: RoutePoint
  goal: RoutePoint
  diagonal?: boolean // 是否允許對角(預設 true)
}

export interface RouteResult {
  path: [number, number][] // [lon, lat] 序列(deck.gl 慣例)
  cost: number
  lengthKm: number
  cells: number[] // 行經的 cells 索引
}

const R_EARTH = 6371
const DEG = Math.PI / 180

export function haversineKm(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const u =
    Math.sin(((bLat - aLat) * DEG) / 2) ** 2 +
    Math.cos(aLat * DEG) * Math.cos(bLat * DEG) * Math.sin(((bLon - aLon) * DEG) / 2) ** 2
  return 2 * R_EARTH * Math.asin(Math.sqrt(u))
}

/** 最小二元堆(優先佇列)，依 f 值取最小。 */
class MinHeap {
  private h: { i: number; f: number }[] = []
  get size(): number {
    return this.h.length
  }
  push(i: number, f: number): void {
    const h = this.h
    h.push({ i, f })
    let c = h.length - 1
    while (c > 0) {
      const p = (c - 1) >> 1
      if (h[p].f <= h[c].f) break
      ;[h[p], h[c]] = [h[c], h[p]]
      c = p
    }
  }
  pop(): number {
    const h = this.h
    const top = h[0]
    const last = h.pop() as { i: number; f: number }
    if (h.length) {
      h[0] = last
      let p = 0
      for (;;) {
        const l = 2 * p + 1
        const r = l + 1
        let m = p
        if (l < h.length && h[l].f < h[m].f) m = l
        if (r < h.length && h[r].f < h[m].f) m = r
        if (m === p) break
        ;[h[p], h[m]] = [h[m], h[p]]
        p = m
      }
    }
    return top.i
  }
}

export function astar(input: AstarInput): RouteResult | null {
  const { cells, step, cost, start, goal, diagonal = true } = input

  const key = (lat: number, lon: number): string =>
    `${Math.round(lat / step)}|${Math.round(lon / step)}`
  const idxByKey = new Map<string, number>()
  cells.forEach((c, i) => idxByKey.set(key(c.lat, c.lon), i))

  const nearest = (p: RoutePoint): number => {
    let best = -1
    let bd = Infinity
    for (let i = 0; i < cells.length; i++) {
      if (!Number.isFinite(cost[i])) continue
      const d = Math.abs(cells[i].lat - p.lat) + Math.abs(cells[i].lon - p.lon)
      if (d < bd) {
        bd = d
        best = i
      }
    }
    return best
  }

  const s = nearest(start)
  const g = nearest(goal)
  if (s < 0 || g < 0) return null

  let minCost = Infinity
  for (const c of cost) if (c < minCost) minCost = c
  const hWeight = Math.max(0.001, minCost) // 每公里最小成本，保持 admissible

  const steps: [number, number][] = diagonal
    ? [
        [step, 0],
        [-step, 0],
        [0, step],
        [0, -step],
        [step, step],
        [step, -step],
        [-step, step],
        [-step, -step],
      ]
    : [
        [step, 0],
        [-step, 0],
        [0, step],
        [0, -step],
      ]

  const gScore = new Array<number>(cells.length).fill(Infinity)
  const came = new Array<number>(cells.length).fill(-1)
  gScore[s] = 0
  const open = new MinHeap()
  open.push(s, haversineKm(cells[s].lat, cells[s].lon, cells[g].lat, cells[g].lon) * hWeight)

  while (open.size) {
    const cur = open.pop()
    if (cur === g) break
    const cc = cells[cur]
    for (const [dLat, dLon] of steps) {
      const nIdx = idxByKey.get(key(cc.lat + dLat, cc.lon + dLon))
      if (nIdx === undefined || !Number.isFinite(cost[nIdx])) continue
      const nc = cells[nIdx]
      const edgeKm = haversineKm(cc.lat, cc.lon, nc.lat, nc.lon)
      const tentative = gScore[cur] + edgeKm * ((cost[cur] + cost[nIdx]) / 2)
      if (tentative < gScore[nIdx]) {
        gScore[nIdx] = tentative
        came[nIdx] = cur
        const h = haversineKm(nc.lat, nc.lon, cells[g].lat, cells[g].lon) * hWeight
        open.push(nIdx, tentative + h)
      }
    }
  }

  if (came[g] < 0 && g !== s) return null

  // 回溯路徑
  const idxPath: number[] = []
  for (let cur = g; cur !== -1; cur = came[cur]) {
    idxPath.push(cur)
    if (cur === s) break
  }
  idxPath.reverse()

  const path: [number, number][] = idxPath.map((i) => [cells[i].lon, cells[i].lat])
  let lengthKm = 0
  for (let i = 1; i < idxPath.length; i++) {
    const a = cells[idxPath[i - 1]]
    const b = cells[idxPath[i]]
    lengthKm += haversineKm(a.lat, a.lon, b.lat, b.lon)
  }
  return { path, cost: gScore[g], lengthKm, cells: idxPath }
}

/** 把多段 A* 結果（起點→中繼1→中繼2→…→終點）串成一條完整航線。 */
export function mergeRouteResults(results: RouteResult[]): RouteResult {
  const path: [number, number][] = []
  const cells: number[] = []
  let cost = 0
  let lengthKm = 0
  results.forEach((r, i) => {
    path.push(...(i === 0 ? r.path : r.path.slice(1))) // 避免相鄰兩段的銜接點重複
    cells.push(...(i === 0 ? r.cells : r.cells.slice(1)))
    cost += r.cost
    lengthKm += r.lengthKm
  })
  return { path, cost, lengthKm, cells }
}
