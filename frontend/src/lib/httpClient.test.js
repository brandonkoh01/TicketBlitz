import { describe, expect, it } from 'vitest'
import { isUuid } from '@/lib/httpClient'

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
