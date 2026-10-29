export type HintKind = 'random_letter' | 'position_letter' | 'eliminate'
export type Economy = {
  coins: number
  inventory: Record<HintKind, number>
  points: Record<'4' | '5' | '6' | 'campaign', number>
}
export type CatalogItem = { id: HintKind; title: string; price: number; description: string }
