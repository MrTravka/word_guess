import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { Economy } from './types'

export function useEconomy(userId?: number) {
  return useQuery({
    queryKey: ['inventory', userId], queryFn: () => api<Economy>('/inventory'),
    enabled: userId !== undefined, retry: false, gcTime: 0,
  })
}
