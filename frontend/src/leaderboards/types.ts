import type { Mode } from '../game/types'

export const modes: { id: Mode; title: string }[] = [
  { id: '4', title: '4 буквы' }, { id: '5', title: '5 букв' },
  { id: '6', title: '6 букв' }, { id: 'campaign', title: 'Кампания' },
]
export type Statistics = {
  mode: Mode; games: number; wins: number; losses: number; surrendered: number; points: number
  win_rate: number; average_attempts: number | null; best_streak: number; current_level: number | null
  attempt_distribution: { attempt: number; wins: number }[]
}
export type Entry = {
  rank: number | null; display_name: string; points: number; wins: number; is_self: boolean; current_level: number | null
}
export type Leaderboard = {
  mode: Mode; page: number; pages: number; total: number; entries: Entry[]; self: Entry; self_page: number | null
  statistics: Statistics
}
