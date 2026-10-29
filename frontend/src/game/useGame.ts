import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api'
import type { Game, Mode } from './types'
import type { HintKind } from '../economy/types'
import { useUpdateGuard } from '../pwa/activity'

type Operation = { path: string; body: Record<string, unknown> }

export function useGame(userId: number, mode: Mode) {
  const client = useQueryClient()
  const key = ['game', userId, mode]
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<Operation | null>(null)
  const [message, setMessage] = useState('')
  const [unauthorized, setUnauthorized] = useState(false)
  const lock = useRef(false)
  const query = useQuery({
    queryKey: key, queryFn: () => api<Game | null>(`/games?mode=${mode}`),
    retry: false, enabled: !busy, refetchOnWindowFocus: !busy, gcTime: 0,
  })
  useUpdateGuard(busy || pending !== null || query.isPending || query.data?.status === 'active')

  async function send(operation: Operation) {
    if (lock.current) return false
    lock.current = true
    setBusy(true)
    setMessage('')
    await client.cancelQueries({ queryKey: key })
    await client.cancelQueries({ queryKey: ['inventory', userId] })
    try {
      const game = await api<Game>(operation.path, 'POST', operation.body)
      client.setQueryData(key, game)
      client.setQueryData(['inventory', userId], game.economy)
      void client.invalidateQueries({ queryKey: ['campaign', userId] })
      if (game.status !== 'active') void client.invalidateQueries({ queryKey: ['leaderboards', userId] })
      setPending(null)
      return true
    } catch (cause) {
      const error = cause as ApiError
      if (error.status === 401) setUnauthorized(true)
      setMessage(error.message)
      if (error.status === 0 || error.status >= 500) setPending(operation)
      else {
        setPending(null)
        if (error.status === 409) await query.refetch()
      }
      return false
    } finally {
      lock.current = false
      setBusy(false)
    }
  }

  function start() {
    if (pending) return Promise.resolve(false)
    return send({ path: '/games', body: { mode, operation_id: crypto.randomUUID() } })
  }

  function action(kind: 'guess' | 'surrender', word?: string) {
    const game = query.data
    if (!game || pending) return Promise.resolve(false)
    return send({
      path: `/games/${game.id}/${kind === 'guess' ? 'guesses' : 'surrender'}`,
      body: { operation_id: crypto.randomUUID(), version: game.version, ...(word === undefined ? {} : { word }) },
    })
  }

  function hint(kind: HintKind, position?: number) {
    const game = query.data
    if (!game || pending) return Promise.resolve(false)
    return send({
      path: `/games/${game.id}/hints`,
      body: { operation_id: crypto.randomUUID(), version: game.version, kind, ...(position === undefined ? {} : { position }) },
    })
  }

  return {
    game: query.data, loading: query.isPending, refreshing: query.isFetching, error: query.error,
    busy, pending: pending !== null, message, unauthorized, start, action, hint,
    retry: () => pending ? send(pending) : query.refetch(),
  }
}
