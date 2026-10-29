import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { Collection } from './types'

export function useCollection(userId: number) {
  return useQuery({ queryKey: ['collection', userId], queryFn: () => api<Collection>('/collection'), retry: false })
}
