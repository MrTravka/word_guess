import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { api } from '../api'
import { audioEngine } from './engine'
import { defaultAudio, type AudioPreferences } from './types'

export function useAudio(userId?: number) {
  const [preferences, setPreferences] = useState(defaultAudio)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const playbackError = useSyncExternalStore(audioEngine.subscribe, audioEngine.snapshot)
  const load = useCallback(async () => {
    const current = ++generation.current
    setLoaded(false)
    if (!userId) return
    try {
      const value = await api<AudioPreferences>('/settings/audio')
      if (generation.current !== current) return
      setPreferences(value)
      audioEngine.configure(value)
      setError('')
      setLoaded(true)
    } catch (cause) { if (generation.current === current) setError((cause as Error).message) }
  }, [userId])
  useEffect(() => {
    audioEngine.lock()
    setPreferences(defaultAudio)
    void load()
    return () => { ++generation.current; audioEngine.lock() }
  }, [load])
  useEffect(() => {
    const unlock = (event: Event) => { if (event.isTrusted) audioEngine.activate() }
    window.addEventListener('pointerdown', unlock, true)
    window.addEventListener('keydown', unlock, true)
    document.addEventListener('visibilitychange', audioEngine.visibility)
    return () => {
      window.removeEventListener('pointerdown', unlock, true)
      window.removeEventListener('keydown', unlock, true)
      document.removeEventListener('visibilitychange', audioEngine.visibility)
    }
  }, [])
  async function save(value: AudioPreferences) {
    const current = generation.current
    const saved = await api<AudioPreferences>('/settings/audio', 'PUT', value)
    if (generation.current === current) {
      setPreferences(saved)
      audioEngine.configure(saved)
    }
  }
  return { preferences, loaded, error, playbackError, load, save }
}
