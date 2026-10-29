import { useEffect, useRef } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { modes, type Leaderboard } from './types'
import StatisticsPanel from './StatisticsPanel'
import shared from '../Account.module.css'
import styles from './Leaderboards.module.css'

export default function LeaderboardsScreen({ userId }: { userId: number }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const mode = modes.find((item) => item.id === params.get('mode'))?.id ?? '5'
  const requestedPage = Number(params.get('page') ?? 1)
  const page = Number.isInteger(requestedPage) && requestedPage >= 1 && requestedPage <= 1000000000 ? requestedPage : 1
  const heading = useRef<HTMLHeadingElement>(null)
  const query = useQuery({
    queryKey: ['leaderboards', userId, mode, page], retry: false,
    queryFn: () => api<Leaderboard>(`/leaderboards?mode=${mode}&page=${page}`),
  })
  const board = query.data
  useEffect(() => { heading.current?.focus() }, [mode, page])
  useEffect(() => {
    if (board && location.hash === '#statistics-heading') {
      document.getElementById('statistics-heading')?.focus()
    }
  }, [board, location.hash])
  const navigate = (next: number) => setParams({ mode, page: String(next) })

  return <section className={styles.screen} aria-labelledby="leaderboards-heading">
    <div className={styles.heading}><h1 id="leaderboards-heading" tabIndex={-1} ref={heading}>Рейтинг</h1>
      <Link className={shared.secondary} to="/#modes-heading">Играть</Link></div>
    <p>За всё время, отдельно для каждого режима. В таблице — игроки с победами.</p>
    <nav className={styles.modes} aria-label="Режим рейтинга">
      {modes.map((item) => <button key={item.id} className={shared.secondary} aria-pressed={mode === item.id}
        onClick={() => setParams({ mode: item.id, page: '1' })}>{item.title}</button>)}
    </nav>
    <p className={styles.help}>Выше тот, у кого больше очков. При равенстве — больше побед, затем раньше достигнут результат.</p>
    <p role="status" aria-live="polite">{query.isPending ? 'Загружаем рейтинг…' : query.isFetching ? 'Обновляем…' : ''}</p>
    {query.error && <p role="alert">{query.error.message}{' '}
      <button className={shared.secondary} onClick={() => { void query.refetch() }}>Повторить</button>{' '}
      <button className={shared.secondary} onClick={() => navigate(1)}>К началу рейтинга</button></p>}
    {board && <>
      <section className={styles.self} aria-label="Ваше место в рейтинге">
        <div><strong>Ваше место: {board.self.rank ?? 'пока нет'}</strong>
          <p>Очки: {board.self.points} · Победы: {board.self.wins}
            {board.self.current_level !== null && ` · Уровень: ${board.self.current_level}`}</p>
          {board.self.rank === null && <p>Выиграйте первую партию в этом режиме, чтобы попасть в рейтинг.</p>}</div>
        <div className={styles.actions}><a className={shared.secondary} href="#statistics-heading">Моя статистика</a>
          {board.self_page !== null && board.self_page !== page && <button className={shared.secondary}
            onClick={() => navigate(board.self_page!)}>К моему месту</button>}</div>
      </section>
      <table className={styles.table}>
        <caption>{modes.find((item) => item.id === mode)?.title} · игроков с победами: {board.total}</caption>
        <thead><tr><th scope="col">Место</th><th scope="col">Игрок</th><th scope="col">Очки</th><th scope="col">Победы</th>
          {mode === 'campaign' && <th scope="col">Уровень</th>}</tr></thead>
        <tbody>{board.entries.map((entry) => <tr key={entry.rank} data-self={entry.is_self}>
          <td>{entry.rank}</td><th scope="row">{entry.display_name}{entry.is_self && <small> · вы</small>}</th>
          <td>{entry.points}</td><td>{entry.wins}</td>{mode === 'campaign' && <td>{entry.current_level}</td>}
        </tr>)}</tbody>
      </table>
      {!board.entries.length && <p>Пока нет побед в этом режиме. Первая строчка может стать вашей.</p>}
      <nav className={styles.pagination} aria-label="Страницы рейтинга">
        <button className={shared.secondary} disabled={page <= 1 || query.isFetching} onClick={() => navigate(page - 1)}>Назад</button>
        <span>Страница {board.page} из {board.pages}</span>
        <button className={shared.secondary} disabled={page >= board.pages || query.isFetching} onClick={() => navigate(page + 1)}>Дальше</button>
      </nav>
      {page !== 1 && <button className={shared.secondary} onClick={() => navigate(1)}>К началу рейтинга</button>}
      <StatisticsPanel statistics={board.statistics} />
    </>}
  </section>
}
