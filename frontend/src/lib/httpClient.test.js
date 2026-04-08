import { afterEach, describe, expect, it, vi } from 'vitest'
import { isUuid, requestJson } from '@/lib/httpClient'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('httpClient.isUuid', () => {
  it('accepts seeded postgres uuid values used in this project', () => {
    expect(isUuid('10000000-0000-0000-0000-000000000301')).toBe(true)
    expect(isUuid('10000000-0000-0000-0000-000000000401')).toBe(true)
  })

  it('accepts regular RFC-like uuids as well', () => {
    expect(isUuid('ea2e16ad-b5be-4803-8ce6-05f9cb93ab20')).toBe(true)
  })

  it('rejects malformed values', () => {
    expect(isUuid('not-a-uuid')).toBe(false)
    expect(isUuid('10000000000000000000000000000301')).toBe(false)
    expect(isUuid('10000000-0000-0000-0000-00000000030')).toBe(false)
    expect(isUuid(null)).toBe(false)
  })
})

describe('httpClient.requestJson', () => {
  it('builds relative API URLs correctly when VITE_API_BASE_URL is /api', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ events: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )

    await requestJson('/events')

    expect(fetchSpy).toHaveBeenCalledWith('/api/events', expect.objectContaining({ method: 'GET' }))
  })

  it('appends query parameters to relative API URLs', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ events: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )

    await requestJson('/events', {
      query: {
        status: 'ACTIVE',
        page: 2,
      },
    })

    expect(fetchSpy).toHaveBeenCalledWith('/api/events?status=ACTIVE&page=2', expect.objectContaining({ method: 'GET' }))
  })
})
