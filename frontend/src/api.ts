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
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method, credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'word_guess' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(8000),
    })
  } catch {
    throw new ApiError(0, 'Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз.')
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'Сервис временно недоступен.')
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}
