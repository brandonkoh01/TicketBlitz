import { afterEach, describe, expect, it, vi } from 'vitest'

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

async function loadComposable({ launchResponse, endResponse, pricingSnapshot } = {}) {
  vi.resetModules()

  const getEvents = vi.fn().mockResolvedValue([
    {
      event_id: '10000000-0000-0000-0000-000000000301',
      name: 'Coldplay Live 2026',
    },
  ])

  const getPricingSnapshot = vi.fn().mockResolvedValue(
    pricingSnapshot || {
      eventID: '10000000-0000-0000-0000-000000000301',
      flashSaleActive: true,
      flashSaleID: 'ea2e16ad-b5be-4803-8ce6-05f9cb93ab20',
      categories: [],
    }
  )

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

  it('maps remaining seats and sold progress for tier rows', async () => {
    const { composable } = await loadComposable({
      pricingSnapshot: {
        eventID: '10000000-0000-0000-0000-000000000301',
        flashSaleActive: true,
        flashSaleID: 'ea2e16ad-b5be-4803-8ce6-05f9cb93ab20',
        categories: [
          {
            categoryID: '30000000-0000-0000-0000-000000000001',
            category: 'CAT1',
            name: 'Category 1',
            currentPrice: '120.00',
            currency: 'SGD',
            status: 'AVAILABLE',
            totalSeats: 40,
            availableSeats: 10,
            soldSeats: 30,
          },
        ],
      },
    })

    expect(composable.tierRows.value).toHaveLength(1)

    const [row] = composable.tierRows.value
    expect(row.range).toBe('10 left / 40 seats')
    expect(row.availableSeats).toBe(10)
    expect(row.soldSeats).toBe(30)
    expect(row.totalSeats).toBe(40)
    expect(row.progressPercent).toBe(75)
  })

  it('uses safe fallback metrics when pricing counts are missing', async () => {
    const { composable } = await loadComposable({
      pricingSnapshot: {
        eventID: '10000000-0000-0000-0000-000000000301',
        flashSaleActive: true,
        flashSaleID: 'ea2e16ad-b5be-4803-8ce6-05f9cb93ab20',
        categories: [
          {
            categoryID: '30000000-0000-0000-0000-000000000002',
            category: 'CAT2',
            name: 'Category 2',
            currentPrice: '90.00',
            currency: 'SGD',
            status: 'SOLD_OUT',
          },
        ],
      },
    })

    expect(composable.tierRows.value).toHaveLength(1)

    const [row] = composable.tierRows.value
    expect(row.range).toBe('0 left')
    expect(row.availableSeats).toBe(0)
    expect(row.soldSeats).toBe(0)
    expect(row.totalSeats).toBe(0)
    expect(row.progressPercent).toBe(100)
    expect(row.status).toBe('sold_out')
  })

  it('infers available seats when payload has total and sold only', async () => {
    const { composable } = await loadComposable({
      pricingSnapshot: {
        eventID: '10000000-0000-0000-0000-000000000301',
        flashSaleActive: true,
        flashSaleID: 'ea2e16ad-b5be-4803-8ce6-05f9cb93ab20',
        categories: [
          {
            categoryID: '30000000-0000-0000-0000-000000000003',
            category: 'CAT3',
            name: 'Category 3',
            currentPrice: '140.00',
            currency: 'SGD',
            status: 'AVAILABLE',
            totalSeats: 50,
            soldSeats: 20,
          },
        ],
      },
    })

    const [row] = composable.tierRows.value
    expect(row.availableSeats).toBe(30)
    expect(row.soldSeats).toBe(20)
    expect(row.totalSeats).toBe(50)
    expect(row.range).toBe('30 left / 50 seats')
    expect(row.progressPercent).toBe(40)
  })

  it('does not undercount sold seats when observed seats exceed stale total', async () => {
    const { composable } = await loadComposable({
      pricingSnapshot: {
        eventID: '10000000-0000-0000-0000-000000000301',
        flashSaleActive: true,
        flashSaleID: 'ea2e16ad-b5be-4803-8ce6-05f9cb93ab20',
        categories: [
          {
            categoryID: '30000000-0000-0000-0000-000000000004',
            category: 'CAT4',
            name: 'Category 4',
            currentPrice: '160.00',
            currency: 'SGD',
            status: 'AVAILABLE',
            totalSeats: 2,
            availableSeats: 1,
            soldSeats: 7,
          },
        ],
      },
    })

    const [row] = composable.tierRows.value
    expect(row.availableSeats).toBe(1)
    expect(row.soldSeats).toBe(7)
    expect(row.totalSeats).toBe(8)
    expect(row.progressPercent).toBe(88)
  })
})
