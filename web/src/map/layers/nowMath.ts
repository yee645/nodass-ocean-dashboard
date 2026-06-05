import type { Species } from '@/data/contracts'

export const OVERALL = '__overall__'

export type RGB = [number, number, number]

interface SuitEnv {
  front?: number | null
  current?: number | null
  u?: number | null
  w?: number | null
  trend?: number | null
}

const clamp = (value: number, min = 0, max = 1): number =>
  Math.max(min, Math.min(max, value))

const bell = (
  value: number | null | undefined,
  optimum: number,
  maxValue: number,
): number => {
  if (value == null || value <= 0) return 0
  const sigma = Math.max(maxValue / 2.5, 0.01)
  return clamp(Math.exp(-((value - optimum) ** 2) / (2 * sigma ** 2)))
}

export function thermalScore(sst: number | null, sp: Species): number {
  if (sst == null) return 0
  const { sst_min: min, opt_lo: optLo, opt_hi: optHi, sst_max: max } = sp
  if (sst <= min || sst >= max) return 0
  const center = (optLo + optHi) / 2
  const sigma = sp.temp_sigma ?? Math.max((optHi - optLo) / 2, 1)
  const score = Math.exp(-((sst - center) ** 2) / (2 * sigma ** 2))
  return optLo <= sst && sst <= optHi ? Math.max(0.72, score) : clamp(score)
}

export function suit(
  sst: number | null,
  sp: Species,
  month: number,
  env: SuitEnv = {},
): number {
  if (sst == null) return 0
  const weights = sp.weights ?? {}
  const wSst = weights.sst ?? 0.6
  const wFront = weights.front ?? 0.15
  const wCurrent = weights.current ?? 0.1
  const wSeason = weights.season ?? 0.15
  const total = Math.max(wSst + wFront + wCurrent + wSeason, 0.01)

  const current =
    env.current ??
    (env.u != null && env.w != null ? Math.hypot(env.u, env.w) : null)
  const seasonScore = sp.season.includes(month) ? 1 : (sp.season_floor ?? 0.45)
  const frontScore = bell(env.front, sp.front_opt ?? 2, sp.front_max ?? 5)
  const currentScore = bell(current, sp.current_opt ?? 0.3, sp.current_max ?? 1)
  const warmSpecies = (sp.opt_lo + sp.opt_hi) / 2 >= 23
  const trend = env.trend ?? null
  const trendBonus =
    trend == null ? 0 : clamp(trend * (warmSpecies ? 1 : -1) * 1.5, -0.05, 0.05)
  const score =
    (thermalScore(sst, sp) * wSst +
      frontScore * wFront +
      currentScore * wCurrent +
      seasonScore * wSeason) /
      total +
    trendBonus

  return Math.round(clamp(score, 0, 1) * 1000) / 10
}

export function scoreBand(v: number): number {
  return Math.min(90, Math.floor(Math.max(0, Math.min(100, v)) / 10) * 10)
}

// 每 10 分一個獨立色相（Spectral：低分冷色、高分暖色），索引 = 級距 / 10
const HEAT_PALETTE: RGB[] = [
  [94, 79, 162], // 0-9
  [50, 136, 189], // 10-19
  [102, 194, 165], // 20-29
  [171, 221, 164], // 30-39
  [230, 245, 152], // 40-49
  [255, 234, 110], // 50-59
  [254, 196, 79], // 60-69
  [253, 141, 60], // 70-79
  [240, 92, 45], // 80-89
  [213, 38, 56], // 90-100
]

export function heat(v: number): RGB {
  return HEAT_PALETTE[scoreBand(v) / 10]
}

export function colorFor(s: number): RGB {
  return s >= 60 ? [215, 38, 61] : s >= 35 ? [240, 162, 2] : [46, 147, 108]
}

const DIR8 = ['北', '東北', '東', '東南', '南', '西南', '西', '西北']

export const bearingDeg = (u: number, w: number): number =>
  ((Math.atan2(u, w) * 180) / Math.PI + 360) % 360

export const dirName = (deg: number): string => DIR8[Math.round(deg / 45) % 8]
