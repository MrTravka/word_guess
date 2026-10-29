import type { Economy, HintKind } from '../economy/types'

export type Mode = '4' | '5' | '6' | 'campaign'
export type Mark = 'correct' | 'present' | 'absent'
export type Guess = { number: number; word: string; marks: Mark[] }
export type Game = {
  id: string
  mode: Mode
  length: number
  max_attempts: number
  status: 'active' | 'won' | 'lost' | 'surrendered'
  version: number
  rules_version: number
  guesses: Guess[]
  keyboard: Partial<Record<string, Mark>>
  economy: Economy
  reward: { points: number; coins: number; hints: number } | null
  campaign: { level: number; current_level: number; stars: number | null; chest_id: string | null } | null
  hints: {
    uses: { kind: HintKind; position: number | null; letter: string | null; removed: string[] }[]
    revealed: Record<string, string>
    unknown_positions: number[]
    options: { kind: HintKind; title: string; price: number; quantity: number; available: boolean; reason: string }[]
    next_win: { points: number; coins: number }
    next_win_with_hint: { points: number; coins: number }
  }
  answer?: {
    word: string
    definition: { text: string; url: string; source: string; license: string; license_url: string } | null
  }
}

export const marks = {
  correct: { symbol: '●', label: 'на своём месте' },
  present: { symbol: '↔', label: 'есть в другом месте' },
  absent: { symbol: '×', label: 'нет доступного совпадения' },
}
