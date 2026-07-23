/**
 * 現在頁 ML SDM 推論（issue #10）：用 build_sdm_now.py 訓練的氣候場多協變數 logistic 係數，
 * 對現在頁即時網格算出 0–100 適合度，取代 nowMath.suit() 的規則式弱版——僅供已訓練魚種；
 * 未訓練或訓練樣本不足的魚種(model.ok=false)，呼叫端仍 fallback 回 suit()，零回歸。
 *
 * 推論特徵對齊 build_sdm_now.py 的 FEAT：
 *   sst(即時值，比訓練用氣候場更準) / sst² / sal_clim / log(chl_clim) / front(即時值現算)
 *   / log(depth+1) / sin(2π·m/12) / cos(2π·m/12)
 * sal/chl/depth 沒有即時來源，用 sdm_now.json 的 env_now(當月氣候場)最近格查詢。
 */
import type { FishCell, SdmNowPayload, SdmNowSpeciesOk } from '@/data/contracts'

const gridKey = (lat: number, lon: number, step: number): string =>
  `${Math.round(lat / step)}|${Math.round(lon / step)}`

/** 即時 SST 網格的原始梯度(中央差分，非正規化)，對齊訓練時 front_clim 的定義方式。 */
function rawFront(grid: FishCell[], step: number): number[] {
  const byKey = new Map<string, number>()
  grid.forEach((c, i) => byKey.set(gridKey(c.lat, c.lon, step), i))
  const at = (i: number | undefined): number | null =>
    i == null || grid[i].v == null ? null : (grid[i].v as number)
  return grid.map((c) => {
    if (c.v == null) return 0
    const e = at(byKey.get(gridKey(c.lat, c.lon + step, step)))
    const w = at(byKey.get(gridKey(c.lat, c.lon - step, step)))
    const n = at(byKey.get(gridKey(c.lat + step, c.lon, step)))
    const s = at(byKey.get(gridKey(c.lat - step, c.lon, step)))
    const gx = e != null && w != null ? (e - w) / 2 : 0
    const gy = n != null && s != null ? (n - s) / 2 : 0
    return Math.hypot(gx, gy)
  })
}

/** env_now(當月氣候場) 最近格查詢：以 0.05° 網格 key 對齊 fishing_grid 的既有步進。 */
function envNowLookup(env: SdmNowPayload['env_now']) {
  const step = 0.05
  const sal = new Map<string, number>()
  const chl = new Map<string, number>()
  const depth = new Map<string, number>()
  for (let i = 0; i < env.lat.length; i++) {
    const key = gridKey(env.lat[i], env.lon[i], step)
    sal.set(key, env.sal[i])
    chl.set(key, env.log_chl[i])
    depth.set(key, env.log_depth[i])
  }
  return (lat: number, lon: number) => {
    const key = gridKey(lat, lon, step)
    return { sal: sal.get(key), chl: chl.get(key), depth: depth.get(key) }
  }
}

const sigmoid = (z: number): number => 1 / (1 + Math.exp(-z))

/**
 * 對整個現在頁網格算 ML 適合度(0–100，對齊 nowMath.suit() 的輸出尺度，可無縫替換)。
 * 回傳 null 表示查無此魚種模型，呼叫端應 fallback 回 suit()；陣列內個別格為 null 表示
 * 該格氣候場查無資料，視同不合格(下游 fishScore 對 null 的處理同 0 分)。
 */
export function mlSuitGrid(
  grid: FishCell[],
  step: number,
  sdmNow: SdmNowPayload | undefined,
  species: string,
  month: number,
): (number | null)[] | null {
  const model = sdmNow?.species[species]
  if (!model || !model.ok) return null
  const m = model as SdmNowSpeciesOk
  const front = rawFront(grid, step)
  const lookup = envNowLookup(sdmNow.env_now)
  const sinM = Math.sin((2 * Math.PI * month) / 12)
  const cosM = Math.cos((2 * Math.PI * month) / 12)
  return grid.map((c, i) => {
    if (c.v == null) return null
    const env = lookup(c.lat, c.lon)
    if (env.sal == null || env.chl == null || env.depth == null) return null
    const sst = c.v
    const x = [sst, sst * sst, env.sal, env.chl, front[i], env.depth, sinM, cosM]
    let z = m.coef[0]
    for (let k = 0; k < x.length; k++) z += ((x[k] - m.mean[k]) / m.std[k]) * m.coef[k + 1]
    return Math.round(sigmoid(z) * 1000) / 10
  })
}
