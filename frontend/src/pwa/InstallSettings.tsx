import type { usePwa } from './usePwa'
import shared from '../Account.module.css'

export default function InstallSettings({ state }: { state: ReturnType<typeof usePwa> }) {
  return <section aria-labelledby="install-heading">
    <h2 id="install-heading">Установка приложения</h2>
    {state.installed ? <p>Приложение открыто в отдельном окне.</p> : <>
      {state.canInstall && <button className={shared.primary} onClick={() => { void state.install() }}>Установить приложение</button>}
      <p className={shared.help}>В Chrome и Edge используйте установку в меню браузера.
        На iPhone/iPad: «Поделиться» → «На экран Домой» в поддерживаемом браузере.</p>
      <p className={shared.help}>Нужен HTTPS или localhost. На телефоне адрес компьютера по обычному HTTP не подходит.
        Для партий требуется соединение с сервером.</p>
    </>}
    {state.message && <p role="status">{state.message}</p>}
  </section>
}
