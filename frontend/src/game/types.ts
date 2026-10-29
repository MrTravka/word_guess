export type Mode = '4' | '5' | '6'
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
