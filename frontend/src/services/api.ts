type ErrorDetails = { field: string; type: string }[]

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: ErrorDetails = [],
  ) { super(message) }
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '')

export async function request<T>(path: string, options: RequestInit = {}, expireOnUnauthorized = true): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.method && !['GET', 'HEAD'].includes(options.method)) {
    headers.set('X-CSRF-Protection', '1')
  }

  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, { ...options, headers, credentials: 'include' })
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiError(0, 'NETWORK_ERROR', '无法连接后端，请稍后重试。')
  }

  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401 && expireOnUnauthorized) {
      window.dispatchEvent(new Event('career:session-expired'))
    }
    throw new ApiError(response.status, body?.error?.code ?? 'REQUEST_FAILED',
      body?.error?.message ?? '请求失败，请稍后重试。', body?.error?.details)
  }
  if (body === null) throw new ApiError(response.status, 'INVALID_RESPONSE', '后端返回了无法读取的响应。')
  return body as T
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '操作失败，请稍后重试。'
}
