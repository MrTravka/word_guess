import { useEffect, useState } from 'react'
import styles from './App.module.css'

type Health = { status: 'ok'; database: 'ready'; version: string }
type State = { status: 'loading' | 'error' } | { status: 'ready'; health: Health }

const modes = [
  { title: '4 буквы', description: 'Короткое слово. Большое начало.', number: '04' },
  { title: '5 букв', description: 'Знакомая длина, новые открытия.', number: '05' },
  { title: '6 букв', description: 'Чуть больше места для догадки.', number: '06' },
  { title: 'Кампания', description: 'Слово за словом, уровень за уровнем.', number: '∞' },
]

export default function App() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 8000)
    let active = true
    setState({ status: 'loading' })
    fetch('/api/health', { cache: 'no-store', signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('Сервис недоступен')
        const health = await response.json() as Health
        if (health.status !== 'ok' || health.database !== 'ready' || typeof health.version !== 'string') {
          throw new Error('Неожиданный ответ сервера')
        }
        if (active) setState({ status: 'ready', health })
      })
      .catch(() => { if (active) setState({ status: 'error' }) })
      .finally(() => window.clearTimeout(timeout))
    return () => { active = false; controller.abort(); window.clearTimeout(timeout) }
  }, [attempt])

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <a className={styles.brand} href="/" aria-label="word_guess — главная">
          <span className={styles.logo} aria-hidden="true">с</span>word_guess
        </a>
        <span className={styles.stage}>Начинаем со слова</span>
      </header>
      <main>
        <section className={styles.hero} aria-labelledby="heading">
          <div>
            <p className={styles.eyebrow}>Маленькие открытия каждый день</p>
            <h1 id="heading">Слово<br />за словом.</h1>
            <p className={styles.intro}>Немного любопытства, знакомые буквы и радость верной догадки.
              Здесь скоро начнётся ваша история слов.</p>
          </div>
          <div className={styles.tiles} aria-label="Слово «слово»">
            {'СЛОВО'.split('').map((letter, index) => (
              <span key={index} className={styles.tile}>{letter}</span>
            ))}
            <p>Пять букв. Столько возможностей.</p>
          </div>
        </section>
        <section className={styles.modes} aria-labelledby="modes-heading">
          <div className={styles.sectionTitle}>
            <h2 id="modes-heading">Четыре пути к ответу</h2><span>Скоро в игре</span>
          </div>
          <div className={styles.cards}>
            {modes.map((mode) => <article className={styles.card} key={mode.title}>
              <span className={styles.modeNumber} aria-hidden="true">{mode.number}</span>
              <h3>{mode.title}</h3><p>{mode.description}</p>
            </article>)}
          </div>
        </section>
        <section className={styles.notice} aria-labelledby="notice-heading">
          <div><h2 id="notice-heading">Всё начинается с основы</h2>
            <p>Сейчас готовится первая версия игры. Регистрация, партии и награды появятся в следующих обновлениях.</p>
          </div>
          <div className={styles.connection} role="status" aria-live="polite">
            <span>{state.status === 'ready' ? '✓ Сервер доступен' : state.status === 'loading'
              ? 'Подключаемся…' : 'Не удалось подключиться'}</span>
            {state.status === 'error' && <button onClick={() => setAttempt((value) => value + 1)}>Повторить</button>}
          </div>
        </section>
      </main>
      <footer className={styles.footer}>
        <span>Играйте в своём ритме.</span>
        <span>{state.status === 'ready' ? `Версия ${state.health.version}` : 'word_guess'}</span>
      </footer>
    </div>
  )
}
