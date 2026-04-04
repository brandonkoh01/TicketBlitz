const DEFAULT_TIMEOUT_MS = 15000

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export class HttpError extends Error {
  constructor(message, { status = 0, data = null } = {}) {
    super(message)
    this.name = 'HttpError'
    this.status = status
    this.data = data
  }
}

function getApiBaseUrl() {
  const baseUrl = import.meta.env.VITE_API_BASE_URL

  if (!baseUrl || typeof baseUrl !== 'string') {
    throw new Error('Missing VITE_API_BASE_URL for API requests.')
  }

  return baseUrl
}

function normalizeErrorMessage(method, path, status, payload) {
  if (payload && typeof payload === 'object') {
    if (typeof payload.error === 'string' && payload.error.trim()) {
      return payload.error
    }

    if (typeof payload.message === 'string' && payload.message.trim()) {
      return payload.message
    }

    if (payload.details && typeof payload.details.message === 'string') {
      return payload.details.message
    }
  }

  return `${method} ${path} failed with status ${status}.`
}

function buildUrl(path, query) {
  const baseUrl = getApiBaseUrl()
  const url = new URL(path, baseUrl)

  if (query && typeof query === 'object') {
    Object.entries(query).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return
      url.searchParams.set(key, String(value))
    })
  }

  return url.toString()
}

async function parseResponseBody(response) {
  const contentType = response.headers.get('content-type') || ''

  if (contentType.includes('application/json')) {
    return response.json()
  }

  const text = await response.text()
  return text ? { message: text } : null
}

export function buildCorrelationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `corr-${Date.now()}-${Math.round(Math.random() * 1e6)}`
}

export function isUuid(value) {
  return typeof value === 'string' && UUID_PATTERN.test(value.trim())
}

export async function requestJson(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : DEFAULT_TIMEOUT_MS
  const requiresOrganiserAuth = Boolean(options.requiresOrganiserAuth)

  const headers = {
    Accept: 'application/json',
    ...(options.headers || {}),
  }

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  if (requiresOrganiserAuth) {
    const organiserKey = import.meta.env.VITE_ORGANISER_API_KEY
    if (!organiserKey || typeof organiserKey !== 'string') {
      throw new Error('Missing VITE_ORGANISER_API_KEY for protected organiser endpoints.')
    }

    headers['x-organiser-api-key'] = organiserKey
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      signal: controller.signal,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })

    const payload = await parseResponseBody(response)

    if (!response.ok) {
      throw new HttpError(normalizeErrorMessage(method, path, response.status, payload), {
        status: response.status,
        data: payload,
      })
    }

    return payload
  } catch (error) {
    if (error instanceof HttpError) {
      throw error
    }

    if (error?.name === 'AbortError') {
      throw new HttpError(`Request timed out after ${timeoutMs}ms.`, {
        status: 408,
        data: null,
      })
    }

    throw new HttpError(error?.message || 'Network request failed.', {
      status: 0,
      data: null,
    })
  } finally {
    clearTimeout(timeoutId)
  }
}
