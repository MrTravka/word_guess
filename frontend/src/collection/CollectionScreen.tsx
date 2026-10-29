import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { useCollection } from './useCollection'
import type { Collection } from './types'
import SkinPreview from './SkinPreview'
import shared from '../Account.module.css'
import styles from './Collection.module.css'

export default function CollectionScreen({ userId }: { userId: number }) {
  const query = useCollection(userId)
  const client = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const lock = useRef(false)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])

  async function choose(skin_id: string | null) {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setMessage('')
    await client.cancelQueries({ queryKey: ['collection', userId] })
    try {
      const result = await api<Collection>('/collection/selection', 'PUT', { skin_id })
      client.setQueryData(['collection', userId], result)
      setMessage('Оформление сохранено.')
    } catch (cause) {
      setMessage((cause as Error).message)
      void query.refetch()
    } finally { lock.current = false; setBusy(false) }
  }

  return <section className={styles.screen} aria-labelledby="collection-heading">
    <div className={styles.heading}><h1 id="collection-heading" tabIndex={-1} ref={heading}>Коллекция</h1>
      <Link to="/chests" className={shared.secondary}>Сундуки</Link></div>
    <p>Шесть оформлений клеток и игрового фона. Получайте скины из сундуков кампании.
      Они сохраняют цвета и обозначения подсказок и не дают игровых преимуществ.</p>
    {query.isPending && <p role="status">Загружаем коллекцию…</p>}
    {query.error && <p role="alert">{query.error.message} <button className={shared.secondary}
      onClick={() => { void query.refetch() }}>Повторить</button></p>}
    {query.data && <>
      <button className={shared.secondary} disabled={busy} aria-pressed={query.data.selected_skin === null}
        onClick={() => { void choose(null) }}>Базовое оформление</button>
      <div className={styles.grid}>{query.data.skins.map((skin) => <article className={styles.card} key={skin.id}>
        <h2>{skin.title}</h2><SkinPreview skinId={skin.id} /><p>{skin.description}</p>
        <button className={shared.primary} disabled={busy || !skin.owned} aria-pressed={query.data.selected_skin === skin.id}
          onClick={() => { void choose(skin.id) }}>{!skin.owned ? 'Пока не получен'
            : query.data.selected_skin === skin.id ? 'Выбран' : `Применить «${skin.title}»`}</button>
      </article>)}</div>
    </>}
    <p role="status" aria-live="polite">{busy ? 'Сохраняем…' : message}</p>
    <Link to="/campaign" className={shared.secondary}>Карта кампании</Link>
  </section>
}
