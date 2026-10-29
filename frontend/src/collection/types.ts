import type { Economy } from '../economy/types'

export type Skin = { id: string; title: string; description: string; owned: boolean }
export type Collection = { skins: Skin[]; selected_skin: string | null }
export type Prize = { kind: 'coins' | 'skin' | 'duplicate'; coins: number; title: string
  rarity: 'common' | 'rare' | 'very_rare'; skin?: Omit<Skin, 'owned'> }
export type Chest = { id: string; level: number; created_at: number
  opening: { operation_key: string; opened_at: number
    result: { table_version: number; prize: Prize; reel: Prize[]; winner_index: number } } | null }
export type Odds = { prizes: (Prize & { percent: number })[]; duplicate_coins: number; skin_count: number }
export type ChestDetail = { chest: Chest; economy: Economy; odds: Odds }
export type ChestPage = { items: Chest[]; page: number; pages: number; unopened: number; opened: number; odds: Odds }
export const rarity = { common: 'Обычная', rare: 'Редкая', very_rare: 'Очень редкая' }
