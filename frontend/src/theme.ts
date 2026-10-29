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
  updateThemeColor()
  try { localStorage.setItem(key, theme) } catch { /* Optional local cache. */ }
}

function updateThemeColor() {
  const theme = document.documentElement.dataset.theme
  const dark = theme === 'dark' || (theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#101713' : '#166534')
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', updateThemeColor)
