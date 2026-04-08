import { afterEach, describe, expect, it, vi } from 'vitest'

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

async function loadComposable({ launchResponse, endResponse } = {}) {
  vi.resetModules()

  const getEvents = vi.fn().mockResolvedValue([
    {
      event_id: '10000000-0000-0000-0000-000000000301',
      name: 'Coldplay Live 2026',
    },
  ])

  const getPricingSnapshot = vi.fn().mockResolvedValue({
    eventID: '10000000-0000-0000-0000-000000000301',
    flashSaleActive: true,
    flashSaleID: 'ea2e16ad-b5be-4803-8ce6-05f9cb93ab20',
    categories: [],
  })

  const getFlashSaleStatus = vi.fn().mockResolvedValue({
    event: { event_id: '10000000-0000-0000-0000-000000000301' },
    pricing: {
      flashSaleID: 'ea2e16ad-b5be-4803-8ce6-05f9cb93ab20',
    },
  })

  const launchFlashSale = vi.fn().mockResolvedValue(
    launchResponse || {
      correlationID: 'corr-launch-1',
      eventName: 'Coldplay Live 2026',
      expiresAt: '2026-04-08T08:00:00Z',
      waitlistCount: 2,
      broadcastPublished: true,
    }
  )

  const endFlashSale = vi.fn().mockResolvedValue(
    endResponse || {
      correlationID: 'corr-end-1',
      waitlistCount: 1,
      broadcastPublished: false,
    }
  )

  const buildCorrelationId = vi.fn(() => 'corr-generated-1')

  class HttpError extends Error {
    constructor(message, status = 500) {
      super(message)
      this.status = status
    }
  }

  vi.doMock('@/lib/httpClient', () => ({
    buildCorrelationId,
    HttpError,
  }))

  vi.doMock('@/lib/scenario2Api', () => ({
    getEvents,
    getPricingSnapshot,
    getFlashSaleStatus,
    launchFlashSale,
    endFlashSale,
  }))

  const { useOrganiserDashboardScenario2 } = await import('./useOrganiserDashboardScenario2.js')
  const composable = useOrganiserDashboardScenario2()

  await flushPromises()
  await flushPromises()

  return {
    composable,
    launchFlashSale,
    endFlashSale,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
})

describe('useOrganiserDashboardScenario2', () => {
  it('builds launch success notice with event name and no UUID leakage', async () => {
    const { composable } = await loadComposable()

    await composable.launchSelectedFlashSale()

    expect(composable.noticeMessage.value).toContain('Flash sale launched for Coldplay Live 2026.')
    expect(composable.noticeMessage.value).toContain('Expires at 08/04/26 04:00 PM SGT.')
    expect(composable.noticeMessage.value).toContain('Broadcast published for 2 waitlisted fans.')
    expect(composable.noticeMessage.value).not.toContain('T08:00:00Z')
    expect(composable.noticeMessage.value).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i)
  })

  it('uses N/A fallback when launch response has no expiresAt', async () => {
    const { composable } = await loadComposable({
      launchResponse: {
        correlationID: 'corr-launch-2',
        eventName: 'Coldplay Live 2026',
        waitlistCount: 2,
        broadcastPublished: true,
      },
    })

    await composable.launchSelectedFlashSale()

    expect(composable.noticeMessage.value).toContain('Expires at N/A.')
  })

  it('falls back to selected event name for end notice when response omits eventName', async () => {
    const { composable } = await loadComposable({
      endResponse: {
        correlationID: 'corr-end-2',
        waitlistCount: 1,
        broadcastPublished: false,
      },
    })

    await composable.endSelectedFlashSale()

    expect(composable.noticeMessage.value).toContain('Flash sale ended for Coldplay Live 2026.')
    expect(composable.noticeMessage.value).toContain('Broadcast was not published even though 1 waitlisted fan was eligible.')
    expect(composable.noticeMessage.value).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i)
  })
})
