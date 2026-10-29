import type { Theme } from './api'

const key = 'word_guess_theme'

export function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(key)
    if (stored === 'light' || stored === 'dark') return stored
  } catch { /* Theme still works when browser storage is unavailable. */ }
  return 'system'
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  try { localStorage.setItem(key, theme) } catch { /* Optional local cache. */ }
}
