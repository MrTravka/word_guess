import { beginWrite } from './pwa/activity'

export type Theme = 'system' | 'light' | 'dark'
export type Account = {
  user: { id: number; login: string; display_name: string }
  settings: { theme: Theme }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const release = ['GET', 'HEAD', 'OPTIONS'].includes(method) ? () => {} : beginWrite()
  try {
    let response: Response
    try {
      if (!navigator.onLine) throw new Error('offline')
      response = await fetch(`/api${path}`, {
        method, credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'word_guess' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(8000),
      })
    } catch {
      window.dispatchEvent(new Event('word-guess-unavailable'))
      throw new ApiError(0, 'Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз.')
    }
    if (!response.ok) {
      if (response.status >= 500) window.dispatchEvent(new Event('word-guess-unavailable'))
      const data = await response.json().catch(() => ({}))
      throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'Сервис временно недоступен.')
    }
    if (response.status === 204) {
      window.dispatchEvent(new Event('word-guess-reachable'))
      return undefined as T
    }
    try {
      const value = await response.json() as T
      window.dispatchEvent(new Event('word-guess-reachable'))
      return value
    }
    catch {
      window.dispatchEvent(new Event('word-guess-unavailable'))
      throw new ApiError(0, 'Ответ прервался. Повторите действие, чтобы восстановить результат.')
    }
  } finally { release() }
}
