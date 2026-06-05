import type { Species } from '@/data/contracts'

export const OVERALL = '__overall__'

export type RGB = [number, number, number]

export function suit(sst: number | null, sp: Species, month: number): number {
  if (sst == null) return 0
  const { sst_min: min, opt_lo: optLo, opt_hi: optHi, sst_max: max } = sp
  let score: number
  if (sst <= min || sst >= max) score = 0
  else if (sst >= optLo && sst <= optHi) score = 1
  else if (sst < optLo) score = (sst - min) / (optLo - min)
  else score = (max - sst) / (max - optHi)
  return Math.round(score * (sp.season.includes(month) ? 1 : 0.55) * 1000) / 10
}

export function heat(v: number): RGB {
  const x = Math.max(0, Math.min(100, v)) / 100
  return [
    Math.round(46 + x * (215 - 46)),
    Math.round(147 - x * (147 - 38)),
    Math.round(108 - x * (108 - 61)),
  ]
}

export function colorFor(s: number): RGB {
  return s >= 60 ? [215, 38, 61] : s >= 35 ? [240, 162, 2] : [46, 147, 108]
}

const DIR8 = ['北', '東北', '東', '東南', '南', '西南', '西', '西北']

export const bearingDeg = (u: number, w: number): number =>
  ((Math.atan2(u, w) * 180) / Math.PI + 360) % 360

export const dirName = (deg: number): string => DIR8[Math.round(deg / 45) % 8]
