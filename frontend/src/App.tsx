import { useEffect, useRef, useState } from 'react'
import AccountForm from './AccountForm'
import SettingsPanel from './SettingsPanel'
import { useAccount } from './useAccount'
import accountStyles from './Account.module.css'
import styles from './App.module.css'
import homeStyles from './Home.module.css'
import { Link, useLocation, useMatch } from 'react-router-dom'
import GameScreen from './game/GameScreen'
import { useEconomy } from './economy/useEconomy'
import ShopScreen from './economy/ShopScreen'
import CampaignScreen from './campaign/CampaignScreen'
import ModeSelection from './ModeSelection'
import CollectionScreen from './collection/CollectionScreen'
import ChestList from './collection/ChestList'
import ChestScreen from './collection/ChestScreen'
import LeaderboardsScreen from './leaderboards/LeaderboardsScreen'
import { useAudio } from './audio/useAudio'
import { usePwa } from './pwa/usePwa'
import UpdateNotice from './pwa/UpdateNotice'
import ConnectionNotice from './pwa/ConnectionNotice'

type Health = { status: 'ok'; database: 'ready'; version: string }
type State = { status: 'loading' | 'error' } | { status: 'ready'; health: Health }

export default function App() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const identity = useAccount()
  const audio = useAudio(identity.account?.user.id)
  const pwa = usePwa()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsButton = useRef<HTMLButtonElement>(null)
  const location = useLocation()
  const match = useMatch('/play/:mode')
  const chestMatch = useMatch('/chests/:chestId')
  const mode = match?.params.mode
  const playing = mode === '4' || mode === '5' || mode === '6' || mode === 'campaign'
  const economy = useEconomy(identity.account?.user.id)
  useEffect(() => {
    const restored = () => setAttempt((value) => value + 1)
    window.addEventListener('word-guess-connected', restored)
    return () => window.removeEventListener('word-guess-connected', restored)
  }, [])

  useEffect(() => {
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView()
  }, [location])

  function closeSettings() {
    setSettingsOpen(false)
    settingsButton.current?.focus()
  }

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
        <Link className={styles.brand} to="/" aria-label="Словоход — главная" onClick={() => setSettingsOpen(false)}>
          <span className={styles.logo} aria-hidden="true">с</span>Словоход
        </Link>
        <nav className={styles.navigation} aria-label="Основная навигация">
          {identity.account && <span className={styles.stage}>{identity.account.user.display_name}</span>}
          {identity.account && <Link className={styles.wallet} to="/shop" aria-label={`Магазин, баланс ${economy.data?.coins ?? 'загружается'} монет`}>
            {economy.data?.coins ?? '…'} <span>монет</span></Link>}
          <button ref={settingsButton} className={accountStyles.secondary}
            disabled={!identity.ready} aria-expanded={settingsOpen}
            onClick={() => setSettingsOpen((open) => !open)}>Настройки</button>
        </nav>
      </header>
      <ConnectionNotice reconnect={identity.reload} />
      <UpdateNotice state={pwa} />
      <main>
        {settingsOpen ? <SettingsPanel account={identity.account} theme={identity.theme}
          saveTheme={identity.saveTheme} logout={identity.logout} close={closeSettings} audio={audio} pwa={pwa} />
          : location.pathname === '/modes' && identity.account ? <ModeSelection />
          : location.pathname === '/shop' && identity.account ? <ShopScreen userId={identity.account.user.id} />
          : location.pathname === '/leaderboards' && identity.account ? <LeaderboardsScreen key={identity.account.user.id}
            userId={identity.account.user.id} />
          : location.pathname === '/collection' && identity.account ? <CollectionScreen key={identity.account.user.id}
            userId={identity.account.user.id} />
          : location.pathname === '/chests' && identity.account ? <ChestList key={identity.account.user.id}
            userId={identity.account.user.id} />
          : chestMatch?.params.chestId && identity.account ? <ChestScreen
            key={`${identity.account.user.id}-${chestMatch.params.chestId}`} userId={identity.account.user.id}
            chestId={chestMatch.params.chestId} />
          : location.pathname === '/campaign' && identity.account ? <CampaignScreen key={identity.account.user.id}
            userId={identity.account.user.id} />
          : playing && identity.account ? <GameScreen key={`${identity.account.user.id}-${mode}`}
            userId={identity.account.user.id} mode={mode} refreshAccount={identity.reload} /> : <>
        {identity.account ? <section className={homeStyles.home} aria-label="Главное меню">
          <div className={homeStyles.content}>
            <p className={homeStyles.description}>Угадайте слово за шесть попыток, ориентируясь на подсказки о буквах.
              {' '}Играйте на 4, 5 или 6 букв или проходите кампанию.</p>
            <div className={homeStyles.actions}>
              <Link className={accountStyles.primary} to="/modes">Играть</Link>
              <Link className={accountStyles.secondary} to="/leaderboards">Рейтинг</Link>
              <Link className={accountStyles.secondary} to="/shop">Магазин</Link>
            </div>
          </div>
        </section> : <section className={styles.hero} aria-labelledby="heading">
          <div>
            <p className={styles.eyebrow}>Маленькие открытия каждый день</p>
            <h1 id="heading">Слово<br />за словом.</h1>
            <p className={styles.intro}>Немного любопытства, знакомые буквы и радость верной догадки. Здесь начнётся ваша история слов.</p>
            {identity.ready && <a className={accountStyles.primary} href="#account">Войти или создать аккаунт</a>}
          </div>
          <div className={styles.tiles} aria-label="Слово «слово»">
            {'СЛОВО'.split('').map((letter, index) => (
              <span key={index} className={styles.tile}>{letter}</span>
            ))}
            <p>Пять букв. Столько возможностей.</p>
          </div>
        </section>}
        {!identity.account && (identity.ready ? <AccountForm authenticate={identity.authenticate} />
          : <section className={accountStyles.panel} aria-label="Аккаунт">
            <p role="status">{identity.error || 'Восстанавливаем сессию…'}</p>
            {identity.error && <button className={accountStyles.secondary} onClick={() => { void identity.reload() }}>Повторить вход</button>}
          </section>)}
        {identity.account && identity.error && <p role="alert" className={accountStyles.error}>
          {identity.error} <button className={accountStyles.secondary} onClick={() => { void identity.reload() }}>Повторить вход</button>
        </p>}
        {!identity.account && <section className={styles.notice} aria-labelledby="notice-heading">
          <div><h2 id="notice-heading">Слово за словом — без спешки</h2>
            <p>Три длины слова, шесть попыток и сколько угодно партий. Побеждайте, получайте монеты и выбирайте подсказки.</p>
          </div>
          <div className={styles.connection} role="status" aria-live="polite">
            <span>{state.status === 'ready' ? '✓ Сервер доступен' : state.status === 'loading'
              ? 'Подключаемся…' : 'Не удалось подключиться'}</span>
            {state.status === 'error' && <button onClick={() => setAttempt((value) => value + 1)}>Повторить</button>}
          </div>
        </section>}
        </>}
      </main>
      <footer className={styles.footer}>
        <span>Играйте в своём ритме.</span>
        <span>{state.status === 'ready' ? `Версия ${state.health.version}` : 'Словоход'}</span>
      </footer>
    </div>
  )
}
