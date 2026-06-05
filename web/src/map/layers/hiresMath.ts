import type { HiresPayload } from '@/data/contracts'

/** 把魚種名解析為 hires layer key（優先 SDM 'S:'，否則適溫 'T:'）。純函式，無 deck 相依。 */
export function resolveHiresKeys(
  layers: HiresPayload['layers'],
  names: string[],
): string[] {
  const keys: string[] = []
  for (const nm of names) {
    if (layers['S:' + nm]) keys.push('S:' + nm)
    else if (layers['T:' + nm]) keys.push('T:' + nm)
  }
  return keys
}
