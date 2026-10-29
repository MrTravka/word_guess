import { defaultAudio, type AudioPreferences } from './types'

type Effect = 'click' | 'reveal' | 'win' | 'chest'

class AudioEngine {
  private preferences = defaultAudio
  private context?: AudioContext
  private music?: HTMLAudioElement
  private gain?: GainNode
  private pauseTimer?: number
  private unlocked = false
  private error = ''
  private listeners = new Set<() => void>()
  subscribe = (callback: () => void) => { this.listeners.add(callback); return () => { this.listeners.delete(callback) } }
  snapshot = () => this.error

  private report(message: string) {
    this.error = message
    this.listeners.forEach((listener) => listener())
  }

  configure(preferences: AudioPreferences) {
    this.preferences = preferences
    this.sync()
  }

  lock() {
    this.unlocked = false
    this.configure(defaultAudio)
  }

  activate() {
    if (document.hidden || (!this.preferences.music_enabled && !this.preferences.sounds_enabled)) return
    try {
      this.context ??= new AudioContext()
      this.unlocked = true
      this.report('')
      void this.context.resume().catch(() => this.report('Нажмите «Включить звук», чтобы разрешить воспроизведение.'))
      this.sync()
    } catch { this.report('Звук недоступен в этом браузере. Игра продолжит работать.') }
  }

  private sync() {
    window.clearTimeout(this.pauseTimer)
    const enabled = this.unlocked && this.preferences.music_enabled && !document.hidden
    try {
      if (enabled && this.context) {
        if (!this.music) {
          this.music = document.createElement('audio')
          this.music.id = 'game-music'
          this.music.src = '/audio/ost.mp3'
          this.music.preload = 'none'
          this.music.loop = true
          this.music.hidden = true
          document.body.append(this.music)
          this.gain = this.context.createGain()
          this.gain.gain.value = 0
          this.context.createMediaElementSource(this.music).connect(this.gain).connect(this.context.destination)
        }
        if (this.music.paused) void this.music.play().catch(() => this.report('Музыка не запустилась. Проверьте соединение и нажмите «Включить звук».'))
      }
      if (this.context && this.gain) {
        const now = this.context.currentTime
        this.gain.gain.cancelScheduledValues(now)
        this.gain.gain.setValueAtTime(this.gain.gain.value, now)
        this.gain.gain.linearRampToValueAtTime(enabled ? this.preferences.music_volume / 100 : 0, now + 0.15)
      }
      if (!enabled) this.pauseTimer = window.setTimeout(() => this.music?.pause(), 160)
    } catch { this.report('Не удалось воспроизвести музыку. Игра продолжит работать.') }
  }

  visibility = () => {
    this.sync()
    if (document.hidden) this.music?.pause()
    // Returning to the page resumes only a previously unlocked player.
  }

  effect(kind: Effect) {
    const context = this.context
    if (!context || context.state !== 'running' || !this.unlocked || document.hidden || !this.preferences.sounds_enabled) return
    const notes = kind === 'click' ? [440] : kind === 'reveal' ? [660] : kind === 'win' ? [523.25, 659.25, 783.99] : [392, 523.25, 783.99]
    const duration = kind === 'click' ? 0.04 : kind === 'reveal' ? 0.12 : 0.28
    notes.forEach((frequency, index) => {
      const start = context.currentTime + index * 0.09
      const oscillator = context.createOscillator()
      const gain = context.createGain()
      oscillator.type = 'sine'
      oscillator.frequency.value = frequency
      gain.gain.setValueAtTime(0, start)
      gain.gain.linearRampToValueAtTime(this.preferences.sounds_volume / 100 * 0.12, start + 0.008)
      gain.gain.exponentialRampToValueAtTime(0.0001, start + duration)
      oscillator.connect(gain).connect(context.destination)
      oscillator.start(start)
      oscillator.stop(start + duration)
      oscillator.onended = () => { oscillator.disconnect(); gain.disconnect() }
    })
  }
}

export const audioEngine = new AudioEngine()
