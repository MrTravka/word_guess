import { useEffect, useRef, useState } from 'react'
import { updateBlocked } from './activity'

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> }

export function usePwa() {
  const [installEvent, setInstallEvent] = useState<InstallEvent | null>(null)
  const [installed, setInstalled] = useState(() => matchMedia('(display-mode: standalone)').matches)
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null)
  const [message, setMessage] = useState('')
  const applying = useRef(false)
  useEffect(() => {
    const beforeInstall = (event: Event) => { event.preventDefault(); setInstallEvent(event as InstallEvent) }
    const installedApp = () => { setInstalled(true); setInstallEvent(null) }
    window.addEventListener('beforeinstallprompt', beforeInstall)
    window.addEventListener('appinstalled', installedApp)
    return () => { window.removeEventListener('beforeinstallprompt', beforeInstall); window.removeEventListener('appinstalled', installedApp) }
  }, [])
  useEffect(() => {
    if (!import.meta.env.PROD || !isSecureContext || !('serviceWorker' in navigator)) return
    let active = true
    let registration: ServiceWorkerRegistration | undefined
    const inspect = () => {
      if (active && registration?.waiting) setWaiting(registration.waiting)
      registration?.installing?.addEventListener('statechange', () => {
        if (active && registration?.waiting) setWaiting(registration.waiting)
      })
    }
    const changed = () => { if (applying.current) window.location.reload() }
    const message = (event: MessageEvent) => {
      if (event.data?.type === 'UPDATE_BLOCKED') {
        applying.current = false
        setMessage('Закройте другие окна игры и повторите обновление между партиями.')
      }
    }
    const check = () => { void registration?.update().catch(() => {}) }
    navigator.serviceWorker.addEventListener('controllerchange', changed)
    navigator.serviceWorker.addEventListener('message', message)
    navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).then((value) => {
      if (!active) return
      registration = value
      registration.addEventListener('updatefound', inspect)
      inspect()
    }).catch(() => { if (active) setMessage('Установка офлайн-оболочки пока недоступна. Попробуйте перезагрузить страницу при наличии сети.') })
    window.addEventListener('online', check)
    window.addEventListener('focus', check)
    return () => {
      active = false
      registration?.removeEventListener('updatefound', inspect)
      navigator.serviceWorker.removeEventListener('controllerchange', changed)
      navigator.serviceWorker.removeEventListener('message', message)
      window.removeEventListener('online', check)
      window.removeEventListener('focus', check)
    }
  }, [])
  async function install() {
    if (!installEvent) return
    try {
      await installEvent.prompt()
      const choice = await installEvent.userChoice
      if (choice.outcome === 'dismissed') setMessage('Установку можно повторить через меню браузера.')
    } catch { setMessage('Используйте установку в меню браузера.') }
    finally { setInstallEvent(null) }
  }
  function update() {
    if (!waiting || updateBlocked() || location.pathname.startsWith('/play/') || !navigator.onLine || document.hidden) return
    applying.current = true
    setMessage('Обновляем приложение…')
    waiting.postMessage({ type: 'APPLY_UPDATE' })
  }
  return { canInstall: installEvent !== null, installed, waiting: waiting !== null, message, install, update }
}
