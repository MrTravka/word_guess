import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { ChestPage } from './types'
import ChestOdds from './ChestOdds'
import shared from '../Account.module.css'
import styles from './Collection.module.css'

export default function ChestList({ userId }: { userId: number }) {
  const [state, setState] = useState<'unopened' | 'opened'>('unopened')
  const [page, setPage] = useState(1)
  const heading = useRef<HTMLHeadingElement>(null)
  const query = useQuery({ queryKey: ['chests', userId, state, page], retry: false,
    queryFn: () => api<ChestPage>(`/chests?state=${state}&page=${page}`) })
  useEffect(() => { heading.current?.focus() }, [state, page])
  return <section className={styles.screen} aria-labelledby="chests-heading">
    <div className={styles.heading}><h1 id="chests-heading" tabIndex={-1} ref={heading}>Сундуки</h1>
      <Link to="/collection" className={shared.secondary}>Коллекция</Link></div>
    <p>Сундук за каждые десять уровней кампании. Открывайте сейчас или возвращайтесь позже.</p>
    <div className={styles.tabs} aria-label="Список сундуков">
      <button className={shared.secondary} aria-pressed={state === 'unopened'} onClick={() => { setState('unopened'); setPage(1) }}>
        Неоткрытые {query.data?.unopened ?? ''}</button>
      <button className={shared.secondary} aria-pressed={state === 'opened'} onClick={() => { setState('opened'); setPage(1) }}>
        История {query.data?.opened ?? ''}</button>
    </div>
    {query.isPending && <p role="status">Загружаем сундуки…</p>}
    {query.error && <p role="alert">{query.error.message} <button className={shared.secondary}
      onClick={() => { void query.refetch() }}>Повторить</button></p>}
    {query.data && <>
      <ChestOdds odds={query.data.odds} />
      {!query.data.items.length && <p>{state === 'unopened' ? 'Пока нет неоткрытых сундуков.' : 'Здесь появятся полученные награды.'}</p>}
      <div className={styles.grid}>{query.data.items.map((chest) => <article className={styles.card} key={chest.id}>
        <h2>◇ Уровень {chest.level}</h2><p>{chest.opening?.result.prize.title ?? 'Ваш сундук ждёт открытия.'}</p>
        {chest.opening && <p>{new Date(chest.opening.opened_at * 1000).toLocaleString('ru-RU')}</p>}
        <Link to={`/chests/${chest.id}`} className={shared.primary}>{chest.opening ? 'Посмотреть награду' : 'К сундуку'}</Link>
      </article>)}</div>
      <div className={styles.tabs}>
        <button className={shared.secondary} disabled={page <= 1} onClick={() => setPage(page - 1)}>Назад</button>
        <span>Страница {page} из {query.data.pages}</span>
        <button className={shared.secondary} disabled={page >= query.data.pages} onClick={() => setPage(page + 1)}>Дальше</button>
      </div>
    </>}
    <Link to="/campaign" className={shared.secondary}>Карта кампании</Link>
  </section>
}
