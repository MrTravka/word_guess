import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, type Account, type Theme } from './api'
import { applyTheme, readTheme } from './theme'

export function useAccount() {
  const [account, setAccount] = useState<Account | null>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')
  const [theme, setTheme] = useState<Theme>(readTheme)
  const generation = useRef(0)
  const mutating = useRef(false)
  const channel = useRef<BroadcastChannel | null>(null)
  const hadAccount = useRef(false)

  const updateTheme = useCallback((value: Theme) => {
    applyTheme(value)
    setTheme(value)
  }, [])

  const accept = useCallback((value: Account | null) => {
    if (value) updateTheme(value.settings.theme)
    else if (hadAccount.current) updateTheme('system')
    hadAccount.current = value !== null
    setAccount(value)
  }, [updateTheme])

  const reload = useCallback(async () => {
    if (mutating.current) return
    const request = ++generation.current
    try {
      const value = await api<Account>('/auth/me')
      if (request !== generation.current) return
      accept(value)
      setError('')
      setReady(true)
    } catch (cause) {
      if (request !== generation.current) return
      if (cause instanceof ApiError && cause.status === 401) {
        accept(null)
        setError('')
        setReady(true)
      } else setError((cause as Error).message)
    }
  }, [accept])

  useEffect(() => {
    void reload()
    window.addEventListener('focus', reload)
    if ('BroadcastChannel' in window) {
      channel.current = new BroadcastChannel('word_guess_account')
      channel.current.onmessage = () => { void reload() }
    }
    return () => {
      ++generation.current
      window.removeEventListener('focus', reload)
      channel.current?.close()
      channel.current = null
    }
  }, [reload])

  async function authenticate(mode: 'login' | 'register', data: Record<string, string>) {
    if (mutating.current) return
    mutating.current = true
    ++generation.current
    try {
      accept(await api<Account>(`/auth/${mode}`, 'POST', data))
      setReady(true)
      setError('')
      channel.current?.postMessage('changed')
    } finally { mutating.current = false }
  }

  async function logout() {
    if (mutating.current) return
    mutating.current = true
    ++generation.current
    try {
      await api<void>('/auth/logout', 'POST')
      accept(null)
      setError('')
      channel.current?.postMessage('changed')
    } finally { mutating.current = false }
  }

  async function saveTheme(value: Theme) {
    if (mutating.current) return
    mutating.current = true
    ++generation.current
    const previous = theme
    updateTheme(value)
    try {
      if (account) {
        const settings = await api<{ theme: Theme }>('/settings', 'PATCH', { theme: value })
        setAccount({ ...account, settings })
        channel.current?.postMessage('changed')
      }
      setError('')
    } catch (cause) {
      updateTheme(previous)
      if (cause instanceof ApiError && cause.status === 401) accept(null)
      throw cause
    } finally { mutating.current = false }
  }

  return { account, ready, error, theme, reload, authenticate, logout, saveTheme }
}
