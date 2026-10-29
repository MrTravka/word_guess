import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

type Level = {
  level: number; length: number; stars: number
  status: 'completed' | 'current' | 'locked'
  milestone: boolean; chest_id: string | null
}
export type Campaign = {
  current_level: number; current_chapter: number; chapter: number; chests: number
  previous_chapter: number | null; next_chapter: number | null; levels: Level[]
}

export function useCampaign(userId?: number, chapter?: number) {
  return useQuery({
    queryKey: ['campaign', userId, chapter ?? 'current'], enabled: Boolean(userId), retry: false,
    queryFn: () => api<Campaign>(`/campaign${chapter ? `?chapter=${chapter}` : ''}`),
  })
}
