import { useEffect, useRef, useState } from 'react'
import type { useAudio } from './useAudio'
import type { AudioPreferences } from './types'
import { audioEngine } from './engine'
import shared from '../Account.module.css'
import styles from './Audio.module.css'
import { useUpdateGuard } from '../pwa/activity'

export default function AudioSettings({ state, signedIn }: { state: ReturnType<typeof useAudio>; signedIn: boolean }) {
  const [draft, setDraft] = useState(state.preferences)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const persisted = useRef(state.preferences)
  useUpdateGuard(busy || JSON.stringify(draft) !== JSON.stringify(state.preferences))
  useEffect(() => { persisted.current = state.preferences; setDraft(state.preferences) }, [state.preferences])
  useEffect(() => () => audioEngine.configure(persisted.current), [])
  function change(value: Partial<AudioPreferences>) {
    const next = { ...draft, ...value }
    setDraft(next)
    setMessage('Изменения ещё не сохранены.')
    audioEngine.configure(next)
    audioEngine.activate()
  }
  async function save() {
    setBusy(true)
    try { await state.save(draft); setMessage('Настройки звука сохранены.') }
    catch (cause) { setMessage((cause as Error).message) }
    finally { setBusy(false) }
  }
  return <section aria-labelledby="audio-heading" className={styles.audio}>
    <h2 id="audio-heading">Музыка и звуки</h2>
    {!signedIn && <p>Войдите, чтобы включить и сохранить звук.</p>}
    {state.error && <p role="alert">{state.error} <button className={shared.secondary}
      onClick={() => { void state.load() }}>Загрузить настройки звука</button></p>}
    <fieldset disabled={!signedIn || !state.loaded || busy}>
      <legend className="srOnly">Настройки звука</legend>
      <label><input type="checkbox" checked={draft.music_enabled} onChange={(event) => change({ music_enabled: event.target.checked })} />Музыка</label>
      <label>Громкость музыки: {draft.music_volume}%<input aria-label="Громкость музыки" type="range" min="0" max="100" step="5"
        value={draft.music_volume} onChange={(event) => change({ music_volume: Number(event.target.value) })} /></label>
      <label><input type="checkbox" checked={draft.sounds_enabled} onChange={(event) => change({ sounds_enabled: event.target.checked })} />Звуковые эффекты</label>
      <label>Громкость эффектов: {draft.sounds_volume}%<input aria-label="Громкость эффектов" type="range" min="0" max="100" step="5"
        value={draft.sounds_volume} onChange={(event) => change({ sounds_volume: Number(event.target.value) })} /></label>
      <div className={styles.actions}>
        <button className={shared.primary} onClick={() => { void save() }}>Сохранить звук</button>
        <button className={shared.secondary} disabled={!draft.sounds_enabled} onClick={() => { audioEngine.activate(); audioEngine.effect('win') }}>Проверить звуки</button>
      </div>
    </fieldset>
    <p className={shared.help}>Музыка запускается после действия в приложении и приостанавливается при скрытии окна.
      Параметры можно прослушать сразу; сохраните их для следующего входа.</p>
    {state.playbackError && <p role="status">{state.playbackError}{' '}
      <button className={shared.secondary} onClick={() => audioEngine.activate()}>Включить звук</button></p>}
    <p role="status" aria-live="polite">{busy ? 'Сохраняем звук…' : message}</p>
  </section>
}
