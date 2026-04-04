import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadScenario2Api({ requestJsonImpl, buildCorrelationIdImpl, isUuidImpl } = {}) {
  vi.resetModules()

  const requestJson = requestJsonImpl || vi.fn()
  const buildCorrelationId = buildCorrelationIdImpl || vi.fn(() => 'corr-test-1')
  const isUuid = isUuidImpl || vi.fn((value) => typeof value === 'string' && value.length === 36)

  vi.doMock('@/lib/httpClient', () => ({
    requestJson,
    buildCorrelationId,
    isUuid,
  }))

  const scenario2Api = await import('./scenario2Api.js')

  return {
    scenario2Api,
    requestJson,
    buildCorrelationId,
    isUuid,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
})

describe('scenario2Api', () => {
  it('fetches event list from /events and returns array fallback', async () => {
    const requestJson = vi.fn().mockResolvedValue({ events: [{ event_id: 'evt-1' }] })
    const { scenario2Api } = await loadScenario2Api({ requestJsonImpl: requestJson })

    const events = await scenario2Api.getEvents()

    expect(events).toEqual([{ event_id: 'evt-1' }])
    expect(requestJson).toHaveBeenCalledWith('/events')
  })

  it('rejects launch payload when eventID is not UUID', async () => {
    const { scenario2Api } = await loadScenario2Api({
      isUuidImpl: vi.fn(() => false),
    })

    await expect(
      scenario2Api.launchFlashSale({
        eventID: 'bad-id',
        discountPercentage: 30,
        durationMinutes: 30,
        escalationPercentage: 20,
      })
    ).rejects.toThrow('eventID must be a valid UUID.')
  })

  it('sends launch request to protected endpoint with normalized payload', async () => {
    const requestJson = vi.fn().mockResolvedValue({ status: 'success' })
    const { scenario2Api } = await loadScenario2Api({ requestJsonImpl: requestJson })

    await scenario2Api.launchFlashSale({
      eventID: '10000000-0000-0000-0000-000000000301',
      discountPercentage: 30,
      durationMinutes: 45,
      escalationPercentage: 20,
    })

    expect(requestJson).toHaveBeenCalledWith('/flash-sale/launch', {
      method: 'POST',
      requiresOrganiserAuth: true,
      body: {
        eventID: '10000000-0000-0000-0000-000000000301',
        discountPercentage: '30',
        durationMinutes: 45,
        escalationPercentage: '20',
        correlationID: 'corr-test-1',
      },
    })
  })

  it('sends end request with supplied correlationID when provided', async () => {
    const requestJson = vi.fn().mockResolvedValue({ status: 'success' })
    const { scenario2Api } = await loadScenario2Api({ requestJsonImpl: requestJson })

    await scenario2Api.endFlashSale({
      eventID: '10000000-0000-0000-0000-000000000301',
      flashSaleID: 'ea2e16ad-b5be-4803-8ce6-05f9cb93ab20',
      correlationID: 'corr-manual-7',
    })

    expect(requestJson).toHaveBeenCalledWith('/flash-sale/end', {
      method: 'POST',
      requiresOrganiserAuth: true,
      body: {
        eventID: '10000000-0000-0000-0000-000000000301',
        flashSaleID: 'ea2e16ad-b5be-4803-8ce6-05f9cb93ab20',
        correlationID: 'corr-manual-7',
      },
    })
  })
})
