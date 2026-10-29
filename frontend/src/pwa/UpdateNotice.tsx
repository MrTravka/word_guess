import type { usePwa } from './usePwa'
import { useUpdateBlocked } from './activity'
import shared from '../Account.module.css'
import { useLocation } from 'react-router-dom'

export default function UpdateNotice({ state }: { state: ReturnType<typeof usePwa> }) {
  const inGame = useLocation().pathname.startsWith('/play/')
  const blocked = useUpdateBlocked() || inGame
  if (!state.waiting) return null
  return <aside className="connectionNotice" aria-label="Обновление приложения">
    <p>Доступна новая версия.{blocked && ' Обновите между партиями: вернитесь к режимам после окончания действия.'}</p>
    <button className={shared.secondary} disabled={blocked} onClick={state.update}>Обновить приложение</button>
    {state.message && <p role="status">{state.message}</p>}
  </aside>
}
