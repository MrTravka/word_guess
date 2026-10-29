import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api'
import type { Mode } from './types'
import { useGame } from './useGame'
import GameBoard from './GameBoard'
import GameKeyboard from './GameKeyboard'
import GameResult from './GameResult'
import HintPanel from './HintPanel'
import shared from '../Account.module.css'
import styles from './Game.module.css'
import { useCollection } from '../collection/useCollection'
import skinStyles from '../collection/skins.module.css'

type Props = { userId: number; mode: Mode; refreshAccount: () => Promise<void> }

export default function GameScreen({ userId, mode, refreshAccount }: Props) {
  const state = useGame(userId, mode)
  const collection = useCollection(userId)
  const { game, busy, pending } = state
  const [draft, setDraft] = useState('')
  const [notice, setNotice] = useState('')
  const [revealRow, setRevealRow] = useState<number | null>(null)
  const [revealing, setRevealing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const seen = useRef<{ id: string; version: number } | null>(null)
  const previousCount = useRef(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const yesButton = useRef<HTMLButtonElement>(null)
  const surrenderButton = useRef<HTMLButtonElement>(null)
  const locked = busy || pending || revealing || confirming || game?.status !== 'active'

  useEffect(() => { heading.current?.focus() }, [])
  useEffect(() => { if (confirming) yesButton.current?.focus() }, [confirming])
  useEffect(() => {
    if (state.unauthorized || (state.error instanceof ApiError && state.error.status === 401)) void refreshAccount()
  }, [state.error, state.unauthorized, refreshAccount])

  useEffect(() => {
    if (!game) return
    const changed = seen.current?.id === game.id && seen.current.version !== game.version
    if (changed || seen.current?.id !== game.id) {
      setDraft('')
      setNotice('')
      setConfirming(false)
    }
    const newRow = changed && game.guesses.length > previousCount.current
    seen.current = { id: game.id, version: game.version }
    previousCount.current = game.guesses.length
    setRevealRow(null)
    setRevealing(false)
    if (!newRow) return
    setRevealRow(game.guesses.length - 1)
    setRevealing(true)
    const duration = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : game.length * 85 + 260
    const timer = window.setTimeout(() => { setRevealing(false); setRevealRow(null) }, duration)
    return () => window.clearTimeout(timer)
  }, [game])

  function press(key: string) {
    if (locked || !game) return
    setNotice('')
    if (key === 'Enter') {
      if (draft.length !== game.length || draft.includes(' ')) setNotice(`Нужно ${game.length} букв.`)
      else void state.action('guess', draft)
    } else if (key === 'Backspace') setDraft((value) => value.trimEnd().slice(0, -1))
    else if (/^[а-яё]$/i.test(key)) setDraft((value) => {
      const letter = key.toLowerCase().replace('ё', 'е')
      return value.includes(' ') ? value.replace(' ', letter) : (value + letter).slice(0, game.length)
    })
  }

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      const target = event.target as HTMLElement
      if (event.altKey || event.ctrlKey || event.metaKey || event.isComposing || event.repeat) return
      if (target.closest('input, textarea, select, [contenteditable="true"]')) return
      if ((event.key === 'Enter' || event.key === ' ') && target.closest('button, a')) return
      if (event.key === 'Enter' || event.key === 'Backspace' || /^[а-яё]$/i.test(event.key)) {
        event.preventDefault()
        press(event.key)
      }
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  })

  async function surrender() {
    setConfirming(false)
    await state.action('surrender')
  }

  return <section className={`${styles.game} ${skinStyles.surface}`} data-skin={collection.data?.selected_skin ?? ''}
    aria-labelledby="game-heading">
    <div className={styles.top}>
      <Link to={mode === 'campaign' ? '/campaign' : '/#modes-heading'} className={shared.secondary}>
        {mode === 'campaign' ? 'Карта' : 'Режимы'}</Link>
      <h1 id="game-heading" ref={heading} tabIndex={-1}>{mode === 'campaign'
        ? `Уровень ${game?.campaign?.level ?? '…'}` : `${mode} ${mode === '4' ? 'буквы' : 'букв'}`}</h1>
      <button className={shared.secondary} disabled={busy || revealing} onClick={() => { void state.retry() }}>Обновить</button>
    </div>
    {state.loading && <p role="status">Восстанавливаем партию…</p>}
    {state.error && <p role="alert" className={shared.error}>{state.error.message}</p>}
    {!state.loading && !state.error && game === null && <div className={styles.start}>
      <p>{mode === 'campaign' ? 'Начните путь по карте. Победа открывает следующий уровень.'
        : `У вас ${mode} ${mode === '4' ? 'буквы' : 'букв'} и шесть попыток. Можно играть без ограничений.`}</p>
      <button className={shared.primary} disabled={busy || pending} onClick={() => { void state.start() }}>Начать партию</button>
    </div>}
    <p className={styles.message} role="status" aria-live="polite">
      {busy ? 'Проверяем…' : notice || state.message || (game?.status === 'active'
        ? `Принято попыток: ${game.guesses.length} из ${game.max_attempts}.` : '')}
    </p>
    {pending && <div className={styles.recovery}>
      <p>Ответ сервера не получен. Повторите действие, чтобы узнать его результат.</p>
      <button className={shared.secondary} disabled={busy} onClick={() => { void state.retry() }}>Повторить действие</button>
    </div>}
    {game && <>
      {Object.keys(game.hints.revealed).length > 0 && <div className={styles.revealed} aria-label="Открытые подсказками позиции">
        <p>{Array.from({ length: game.length }, (_, index) => game.hints.revealed[String(index)]?.toUpperCase() ?? '·').join(' ')}</p>
        <button className={shared.secondary} disabled={locked} onClick={() => setDraft((value) => Array.from({ length: game.length },
          (_, index) => value[index] || game.hints.revealed[String(index)] || ' ').join(''))}>Подставить открытые буквы</button>
      </div>}
      <GameBoard game={game} draft={draft} revealRow={revealRow} />
      <div className={styles.legend} aria-label="Обозначения клеток">
        <span>● На месте</span><span>↔ В другом месте</span><span>× Нет совпадения</span>
      </div>
      {game.status === 'active' ? <>
        <GameKeyboard game={game} disabled={locked} press={press} />
        <HintPanel key={game.id} game={game} disabled={busy || pending || revealing || confirming} apply={state.hint} />
        <details className={styles.rules}><summary>Как играть</summary>
          <p>Введите существительное в начальной форме и нажмите «Ввод» или Enter. Буквы с клавиатуры должны быть русскими; Ё принимается как Е.</p>
          <p>Неизвестное слово, неверная длина и повтор не тратят попытку. Каждая повторяющаяся буква учитывается по числу вхождений в ответ.</p>
          <p>Можно выйти к режимам и продолжить позже. Чтобы начать заново, завершите партию или сдайте её.</p>
        </details>
        {confirming ? <div className={styles.confirmation} role="group" aria-label="Подтверждение сдачи">
          <p>Завершить партию и узнать ответ? Это будет поражение.</p>
          <button ref={yesButton} className={shared.secondary} onClick={() => { void surrender() }}>Да, завершить</button>
          <button className={shared.secondary} onClick={() => { setConfirming(false); surrenderButton.current?.focus() }}>Продолжить играть</button>
        </div> : <button ref={surrenderButton} className={styles.surrender} disabled={busy || pending || revealing}
          onClick={() => setConfirming(true)}>Сдаться</button>}
      </> : !revealing && <GameResult game={game} busy={busy || pending} start={() => { void state.start() }} />}
    </>}
  </section>
}
