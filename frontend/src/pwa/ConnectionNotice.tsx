import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import shared from '../Account.module.css'

export default function ConnectionNotice({ reconnect }: { reconnect: () => Promise<void> }) {
  const [connected, setConnected] = useState(navigator.onLine)
  const [checking, setChecking] = useState(false)
  const connection = useRef(navigator.onLine)
  const lock = useRef(false)
  const active = useRef(true)
  const client = useQueryClient()
  const check = useCallback(async () => {
    if (lock.current || !navigator.onLine) return
    lock.current = true
    setChecking(true)
    try {
      const response = await fetch('/api/health', { cache: 'no-store', signal: AbortSignal.timeout(3000) })
      if (!active.current || !response.ok) return
      const wasDisconnected = !connection.current
      connection.current = true
      setConnected(true)
      if (wasDisconnected) {
        await reconnect()
        void client.invalidateQueries()
        window.dispatchEvent(new Event('word-guess-connected'))
      }
    } catch { /* The notice remains visible until a successful health request. */ }
    finally { lock.current = false; if (active.current) setChecking(false) }
  }, [client, reconnect])
  useEffect(() => {
    active.current = true
    const offline = () => { connection.current = false; setConnected(false) }
    const online = () => { void check() }
    const reachable = () => { if (!connection.current) void check() }
    window.addEventListener('offline', offline)
    window.addEventListener('word-guess-unavailable', offline)
    window.addEventListener('word-guess-reachable', reachable)
    window.addEventListener('online', online)
    window.addEventListener('focus', online)
    const timer = window.setInterval(() => { if (!connection.current) void check() }, 15000)
    return () => {
      active.current = false
      window.removeEventListener('offline', offline)
      window.removeEventListener('word-guess-unavailable', offline)
      window.removeEventListener('word-guess-reachable', reachable)
      window.removeEventListener('online', online)
      window.removeEventListener('focus', online)
      window.clearInterval(timer)
    }
  }, [check])
  return connected ? null : <aside className="connectionNotice" aria-label="Соединение с сервером">
    <p role="status">Нет связи с сервером. Для партий и покупок нужна сеть. Прогресс сохранён на сервере.</p>
    <p className={shared.help}>Если ответ на действие потерялся, после подключения нажмите его кнопку повтора.</p>
    <button className={shared.secondary} disabled={checking} onClick={() => { void check() }}>
      {checking ? 'Проверяем связь…' : 'Проверить соединение'}</button>
  </aside>
}
