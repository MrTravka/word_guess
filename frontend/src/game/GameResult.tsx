import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import type { Game } from './types'
import shared from '../Account.module.css'
import styles from './Game.module.css'

export default function GameResult({ game, busy, start }: { game: Game; busy: boolean; start: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [game.id])
  const definition = game.answer?.definition
  return <section className={styles.result} aria-labelledby="result-heading">
    <h2 id="result-heading" tabIndex={-1} ref={heading}>
      {game.status === 'won' ? 'Слово найдено!' : game.status === 'surrendered' ? 'Партия завершена' : 'В этот раз не получилось'}
    </h2>
    <p>Загаданное слово: <strong className={styles.answer}>{game.answer?.word}</strong></p>
    {definition ? <>
      <p className={styles.definition}>{definition.text}</p>
      <p className={styles.source}><a href={definition.url} target="_blank" rel="noreferrer">{definition.source}</a>
        {' · '}<a href={definition.license_url} target="_blank" rel="noreferrer">{definition.license}</a>
        {' · '}выбрано одно значение, текст сокращён</p>
    </> : <p className={styles.source}>Для этого слова толкование пока не добавлено.</p>}
    <p className={styles.source}>Использовано попыток: {game.guesses.length} из {game.max_attempts}.</p>
    {game.reward && <p className={styles.earned}>Награда: <strong>{game.reward.points} очков</strong> и <strong>{game.reward.coins} монет</strong>.
      {' '}Использовано подсказок: {game.reward.hints}.</p>}
    {game.campaign && <>
      {game.campaign.stars && <p aria-label={`Звёзд: ${game.campaign.stars}`}>{'★'.repeat(game.campaign.stars)}</p>}
      {game.campaign.chest_id && <p>Сундук за уровень {game.campaign.level} сохранён!{' '}
        <Link className={shared.secondary} to={`/chests/${game.campaign.chest_id}`}>Открыть сундук</Link></p>}
      <p><Link to="/campaign" className={shared.secondary}>Карта кампании</Link></p>
    </>}
    <button className={shared.primary} disabled={busy} onClick={start}>{game.campaign
      ? game.status === 'won' ? 'Следующий уровень' : 'Попробовать другое слово' : 'Следующее слово'}</button>
    <p><Link className={shared.secondary} to={`/leaderboards?mode=${game.mode}#statistics-heading`}>Моя статистика</Link></p>
  </section>
}
