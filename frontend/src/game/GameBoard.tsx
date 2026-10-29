import type { CSSProperties } from 'react'
import { marks, type Game } from './types'
import styles from './Game.module.css'

type Props = { game: Game; draft: string; revealRow: number | null }

export default function GameBoard({ game, draft, revealRow }: Props) {
  return <div className={styles.board} role="group" aria-label={`Поле: ${game.length} букв, ${game.max_attempts} попыток`}>
    {Array.from({ length: game.max_attempts }, (_, row) => {
      const guess = game.guesses[row]
      const current = !guess && row === game.guesses.length && game.status === 'active'
      const letters = guess?.word ?? (current ? draft : '')
      const label = guess
        ? `Попытка ${row + 1}: ${guess.word.toUpperCase()}. ${guess.marks.map((mark, i) => `${guess.word[i]} — ${marks[mark].label}`).join('; ')}`
        : `Попытка ${row + 1}${current ? `, ввод: ${draft || 'пусто'}` : ', пусто'}`
      return <div key={row} className={styles.row} role="group" aria-label={label}
        style={{ gridTemplateColumns: `repeat(${game.length}, 1fr)` }}>
        {Array.from({ length: game.length }, (_, column) => {
          const mark = guess?.marks[column]
          return <span key={column} aria-hidden="true"
            data-mark={mark} data-filled={Boolean(letters[column]?.trim())}
            className={`${styles.cell} ${row === revealRow && mark ? styles.reveal : ''}`}
            style={{ '--delay': `${column * 85}ms` } as CSSProperties}>
            {letters[column]?.toUpperCase()}
            {mark && <small>{marks[mark].symbol}</small>}
          </span>
        })}
      </div>
    })}
  </div>
}
