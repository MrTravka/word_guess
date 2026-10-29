import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api'
import { operationId } from '../operationId'
import type { ChestDetail } from './types'
import { rarity } from './types'
import ChestOdds from './ChestOdds'
import ChestReel from './ChestReel'
import shared from '../Account.module.css'
import styles from './Collection.module.css'
import { audioEngine } from '../audio/engine'
import { useUpdateGuard } from '../pwa/activity'

export default function ChestScreen({ userId, chestId }: { userId: number; chestId: string }) {
  const client = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [animating, setAnimating] = useState(false)
  const lock = useRef(false)
  useUpdateGuard(busy || pending !== null)
  const heading = useRef<HTMLHeadingElement>(null)
  const resultHeading = useRef<HTMLHeadingElement>(null)
  const key = ['chest', userId, chestId]
  const query = useQuery({ queryKey: key, queryFn: () => api<ChestDetail>(`/chests/${chestId}`), retry: false,
    enabled: !busy && !pending, refetchOnWindowFocus: !busy && !pending })
  const opening = query.data?.chest.opening
  const prize = opening?.result.prize
  const finish = useCallback(() => setAnimating(false), [])
  useEffect(() => { heading.current?.focus() }, [])
  useEffect(() => { if (opening && !animating) resultHeading.current?.focus() }, [opening, animating])

  async function open() {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setMessage('')
    const operation_id = pending ?? operationId()
    await client.cancelQueries({ queryKey: key })
    await client.cancelQueries({ queryKey: ['inventory', userId] })
    try {
      const result = await api<ChestDetail>(`/chests/${chestId}/open`, 'POST', { operation_id })
      client.setQueryData(key, result)
      client.setQueryData(['inventory', userId], result.economy)
      setAnimating(true)
      audioEngine.effect('chest')
      setPending(null)
      for (const prefix of ['chests', 'campaign', 'collection']) {
        void client.invalidateQueries({ queryKey: [prefix, userId] })
      }
    } catch (cause) {
      const error = cause as ApiError
      setMessage(error.message)
      setPending(error.status === 0 || error.status >= 500 ? operation_id : null)
      if (error.status === 409) void query.refetch()
    } finally { lock.current = false; setBusy(false) }
  }

  return <section className={styles.screen} aria-labelledby="chest-heading">
    <div className={styles.heading}><h1 id="chest-heading" ref={heading} tabIndex={-1}>
      Сундук {query.data ? `за уровень ${query.data.chest.level}` : ''}</h1>
      <Link className={shared.secondary} to="/chests">Все сундуки</Link></div>
    {query.isPending && <p role="status">Загружаем сундук…</p>}
    {query.error && <p role="alert">{query.error.message} <button className={shared.secondary}
      onClick={() => { void query.refetch() }}>Повторить</button></p>}
    {query.data && <>
      <ChestOdds odds={query.data.odds} />
      {!opening && !pending && <><p>Монеты или скин для вашей коллекции. Сундук можно открыть позже.</p>
        <button className={shared.primary} disabled={busy} onClick={() => { void open() }}>Открыть сундук</button></>}
      {opening && (animating ? <ChestReel opening={opening} finish={finish} /> : <div className={styles.result}>
        <h2 tabIndex={-1} ref={resultHeading}>Ваша награда: {prize?.title}</h2>
        <p>{prize && rarity[prize.rarity]} награда · сохранена в аккаунте</p>
        {prize?.kind === 'duplicate' && <p>Этот скин уже есть. Начислено {prize.coins} монет компенсации.</p>}
        <Link className={shared.primary} to={prize?.kind === 'skin' ? '/collection' : '/campaign'}>
          {prize?.kind === 'skin' ? 'В коллекцию' : 'Продолжить кампанию'}</Link>
      </div>)}
    </>}
    <p role="status" aria-live="polite">{busy ? 'Открываем…' : message}</p>
    {pending && <><p>Ответ не получен. Повторите запрос, чтобы восстановить награду.</p>
      <button className={shared.primary} disabled={busy} onClick={() => { void open() }}>Восстановить открытие</button></>}
  </section>
}
