import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { HintKind } from '../economy/types'
import type { Game } from './types'
import shared from '../Account.module.css'
import styles from './Hints.module.css'

type Props = { game: Game; disabled: boolean; apply: (kind: HintKind, position?: number) => Promise<boolean> }

export default function HintPanel({ game, disabled, apply }: Props) {
  const [choice, setChoice] = useState<HintKind | null>(null)
  const [position, setPosition] = useState<number | undefined>()
  const selected = game.hints.options.find((option) => option.kind === choice)

  async function confirm() {
    if (!choice) return
    await apply(choice, position)
    setChoice(null)
    setPosition(undefined)
  }

  return <section className={styles.hints} aria-label="Подсказки">
    <div className={styles.top}><h2>Подсказки</h2><Link to="/shop">Магазин · {game.economy.coins} монет</Link></div>
    <p className={styles.impact}>При победе на следующей попытке: {game.hints.next_win.points} очков.
      {' '}С ещё одной подсказкой: {game.hints.next_win_with_hint.points}. Монеты: {game.hints.next_win.coins}.</p>
    <div className={styles.options}>
      {game.hints.options.map((option) => <div key={option.kind} className={styles.option}>
        <button className={shared.secondary} disabled={disabled || Boolean(choice) || !option.available}
          onClick={() => { setChoice(option.kind); setPosition(undefined) }}>{option.title} · {option.quantity}</button>
        <p>{option.price} монет в магазине{option.reason ? ` · ${option.reason}` : ''}</p>
      </div>)}
    </div>
    {selected && <div className={styles.confirm} role="group" aria-label="Подтверждение подсказки">
      <h3>{selected.title}</h3>
      <p>Потратить один предмет из инвентаря? Подсказка не расходует попытку и уменьшает очки за победу.</p>
      {choice === 'position_letter' && <fieldset disabled={disabled} className={styles.positions}>
        <legend>Выберите неизвестную позицию</legend>
        {game.hints.unknown_positions.map((index) => <label key={index}>
          <input type="radio" name="hint-position" checked={position === index} onChange={() => setPosition(index)} />
          {index + 1}
        </label>)}
      </fieldset>}
      <button className={shared.primary} disabled={disabled || !selected.available || (choice === 'position_letter' && position === undefined)}
        onClick={() => { void confirm() }}>Применить подсказку</button>
      <button className={shared.secondary} disabled={disabled} onClick={() => setChoice(null)}>Отмена</button>
    </div>}
  </section>
}
