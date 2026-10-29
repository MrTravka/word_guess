import { useState, type SubmitEvent } from 'react'
import styles from './Account.module.css'

type Props = {
  authenticate: (mode: 'login' | 'register', data: Record<string, string>) => Promise<void>
}

export default function AccountForm({ authenticate }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('register')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const data = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>
    setBusy(true)
    setError('')
    try { await authenticate(mode, data) }
    catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  return <section id="account" className={styles.panel} aria-labelledby="account-heading">
    <div className={styles.heading}>
      <div><p className={styles.eyebrow}>Ваше место для открытий</p>
        <h2 id="account-heading">{mode === 'register' ? 'Начнём знакомство' : 'С возвращением'}</h2></div>
      <div className={styles.switcher} aria-label="Действие с аккаунтом">
        <button type="button" aria-pressed={mode === 'register'} disabled={busy}
          onClick={() => { setMode('register'); setError('') }}>Регистрация</button>
        <button type="button" aria-pressed={mode === 'login'} disabled={busy}
          onClick={() => { setMode('login'); setError('') }}>Вход</button>
      </div>
    </div>
    <p className={styles.muted}>Только логин и пароль. Без почты и подтверждений.</p>
    <form key={mode} onSubmit={submit} className={styles.form} aria-busy={busy}>
      <fieldset disabled={busy} className={styles.fields}>
        {mode === 'register' && <label>Как вас называть
          <input name="display_name" autoComplete="nickname" maxLength={40} required placeholder="Ваше имя" />
        </label>}
        <label>Логин<input name="login" autoComplete="username" autoCapitalize="none" spellCheck={false}
          minLength={3} maxLength={32} required aria-describedby="login-help" placeholder="Например, slovolyub" /></label>
        <label>Пароль<input name="password" type="password" autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
          minLength={8} maxLength={128} required aria-describedby="password-help" placeholder="Не менее 8 символов" /></label>
      </fieldset>
      <p id="login-help" className={styles.help}>Логин: 3–32 русские или латинские буквы, цифры или _. Регистр не важен.</p>
      <p id="password-help" className={styles.help}>Пароль: от 8 до 128 символов. Сохраните его — восстановление пока недоступно.</p>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <button className={styles.primary} disabled={busy} type="submit">
        {busy ? 'Подождите…' : mode === 'register' ? 'Создать аккаунт' : 'Войти'}
      </button>
    </form>
  </section>
}
