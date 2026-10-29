import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Account, Theme } from './api'
import styles from './Account.module.css'
import AudioSettings from './audio/AudioSettings'
import type { useAudio } from './audio/useAudio'
import type { usePwa } from './pwa/usePwa'
import InstallSettings from './pwa/InstallSettings'

type Props = {
  account: Account | null
  theme: Theme
  saveTheme: (theme: Theme) => Promise<void>
  logout: () => Promise<void>
  close: () => void
  audio: ReturnType<typeof useAudio>
  pwa: ReturnType<typeof usePwa>
}

export default function SettingsPanel({ account, theme, saveTheme, logout, close, audio, pwa }: Props) {
  const heading = useRef<HTMLHeadingElement>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { heading.current?.focus() }, [])

  async function choose(value: Theme) {
    if (busy) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await saveTheme(value)
      setMessage(account ? 'Тема сохранена в аккаунте.' : 'Тема выбрана для этого браузера.')
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function leave() {
    setBusy(true)
    setError('')
    try { await logout(); close() }
    catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  return <section className={styles.panel} aria-labelledby="settings-heading">
    <div className={styles.heading}>
      <h1 id="settings-heading" tabIndex={-1} ref={heading}>Настройки</h1>
      <button className={styles.secondary} onClick={close} disabled={busy}>На главную</button>
    </div>
    {account && <p>Вы вошли как <strong>{account.user.display_name}</strong> · @{account.user.login}</p>}
    {account && <p><Link className={styles.secondary} to="/collection" onClick={close}>Коллекция и сундуки</Link></p>}
    {account && <p><Link className={styles.secondary} to="/leaderboards#statistics-heading" onClick={close}>Моя статистика</Link></p>}
    <fieldset className={styles.preferences} disabled={busy}>
      <legend>Оформление</legend>
      <div className={styles.themes}>
        {([['system', 'Системная'], ['light', 'Светлая'], ['dark', 'Тёмная']] as const).map(([value, title]) => (
          <label key={value}><input type="radio" name="theme" value={value} checked={theme === value}
            onChange={() => { void choose(value) }} />{title}</label>
        ))}
      </div>
    </fieldset>
    <p className={styles.muted}>Системная тема следует настройкам устройства.
      {account ? ' Ваш выбор доступен и при входе с другого устройства.' : ' Войдите, чтобы сохранить выбор в аккаунте.'}</p>
    <p role="status" className={styles.help}>{busy ? 'Сохраняем…' : message}</p>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    <AudioSettings state={audio} signedIn={Boolean(account)} />
    <InstallSettings state={pwa} />
    {account && <button className={styles.secondary} disabled={busy} onClick={() => { void leave() }}>Выйти из аккаунта</button>}
  </section>
}
