const base = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
export const SESSION_KEY = 'studymate.session'
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}
export function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail
      .map(
        (error) =>
          `${error.loc?.filter((v: string) => v !== 'body').join(' → ') || 'Request'}: ${error.msg || 'Invalid value'}`,
      )
      .join('; ')
  if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message)
  return 'Something went wrong. Please try again.'
}
export async function request<T>(
  path: string,
  token?: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData))
    headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(`${base}${path}`, { ...options, headers })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'We couldn’t connect to Study Mate. Check your connection and try again.')
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    if (response.status === 401 && token)
      window.dispatchEvent(new CustomEvent('studymate:unauthorized', { detail: token }))
    throw new ApiError(response.status, detailMessage(data.detail), data.detail?.request_id)
  }
  const type = response.headers.get('content-type') || ''
  if (type.includes('application/pdf') || type.includes('audio/') || type.includes('image/'))
    return (await response.blob()) as T
  if (response.status === 204) return undefined as T
  return response.json()
}
export const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })
export async function allPages<T>(path: string, token: string): Promise<T[]> {
  const results: T[] = []
  for (let offset = 0; ; offset += 100) {
    const batch = await request<T[]>(
      `${path}${path.includes('?') ? '&' : '?'}limit=100&offset=${offset}`,
      token,
    )
    results.push(...batch)
    if (batch.length < 100) return results
  }
}
export function readSession(): { token: string; expiresAt: number } | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null')
    return value?.token && value.expiresAt > Date.now() ? value : null
  } catch {
    return null
  }
}
export function dateLabel(value: string) {
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
export function fileSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
export function isAbort(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}
