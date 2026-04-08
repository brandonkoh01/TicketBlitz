import { describe, expect, it } from 'vitest'
import { formatDateTimeSGT } from './dateTimeFormat'

describe('formatDateTimeSGT', () => {
  it('formats ISO timestamps into compact Singapore time', () => {
    expect(formatDateTimeSGT('2026-04-08T08:00:00Z')).toBe('08/04/26 04:00 PM SGT')
  })

  it('returns fallback for empty values', () => {
    expect(formatDateTimeSGT(null)).toBe('Not available')
    expect(formatDateTimeSGT(undefined, { fallback: 'N/A' })).toBe('N/A')
  })

  it('returns fallback for invalid values', () => {
    expect(formatDateTimeSGT('invalid-date')).toBe('Not available')
    expect(formatDateTimeSGT('invalid-date', { fallback: 'Date pending' })).toBe('Date pending')
  })
})
