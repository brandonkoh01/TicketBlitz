import { afterEach, describe, expect, it, vi } from 'vitest'

const EVENT_ID = '10000000-0000-0000-0000-000000000301'
const RICHARD_EVENT_ID = '10000000-0000-0000-0000-000000000501'
const WAITLIST_ID = '12c46907-09c8-4f66-bcb2-5ac3480ef9e2'

async function mountPage({
  waitlistState,
  reserveError,
  routeQuery = {},
  eventsPayload = [
    {
      event_id: EVENT_ID,
      event_code: 'EVT-301',
      name: 'Coldplay Live 2026',
      status: 'ACTIVE',
    },
  ],
  categoriesByEventID = {
    [EVENT_ID]: [
      {
        category_id: '20000000-0000-0000-0000-000000000102',
        category_code: 'CAT2',
        name: 'Category 2',
        current_price: 120,
        currency: 'SGD',
      },
    ],
  },
}) {
  vi.resetModules()

  const push = vi.fn().mockResolvedValue(undefined)
  const apiGet = vi.fn(async (path) => {
    if (path === '/events') {
      return {
        events: eventsPayload,
      }
    }

    if (path.startsWith('/event/') && path.endsWith('/categories')) {
      const eventID = path.slice('/event/'.length, -'/categories'.length)
      return {
        categories: categoriesByEventID[eventID] || [],
      }
    }

    if (path === '/reserve/waitlist/my') {
      throw new Error('Unexpected waitlist lookup call')
    }

    throw new Error(`Unexpected GET ${path}`)
  })

  const reserve = vi.fn(async () => {
    throw reserveError
  })

  vi.doMock('vue-router', () => {
    return {
      useRoute: () => ({ params: {}, query: routeQuery }),
      useRouter: () => ({ push }),
      RouterLink: {
        name: 'RouterLink',
        props: {
          to: {
            type: [String, Object],
            required: true,
          },
        },
        template: '<a><slot /></a>',
      },
    }
  })

  vi.doMock('@/composables/useApiClient', () => ({
    useApiClient: () => ({
      get: apiGet,
    }),
  }))

  vi.doMock('@/composables/useScenarioReservation', async () => {
    const { ref } = await import('vue')

    return {
      useScenarioReservation: () => ({
        reserve,
        errorMessage: ref(''),
      }),
    }
  })

  vi.doMock('@/stores/scenarioFlowStore', () => ({
    useScenarioFlowStore: () => ({
      state: {
        waitlist: waitlistState,
      },
    }),
  }))

  const { createApp, nextTick } = await import('vue')
  const { default: TicketPurchasePage } = await import('./TicketPurchasePage.vue')

  const container = document.createElement('div')
  document.body.appendChild(container)

  const app = createApp(TicketPurchasePage)
  app.component('AppTopNav', {
    props: {
      pageLabel: { type: String, default: '' },
      showSearch: { type: Boolean, default: false },
    },
    template: '<div><slot name="actions" /></div>',
  })
  app.component('SectionLabel', {
    props: {
      index: { type: String, default: '' },
      label: { type: String, default: '' },
    },
    template: '<div data-test="section-label" />',
  })
  app.component('UiButton', {
    props: {
      to: { type: [String, Object], default: null },
      variant: { type: String, default: 'primary' },
    },
    template: '<button><slot /></button>',
  })
  app.component('RouterLink', {
    props: {
      to: {
        type: [String, Object],
        required: true,
      },
    },
    template: '<a><slot /></a>',
  })
  app.mount(container)

  await nextTick()
  await Promise.resolve()
  await nextTick()

  return {
    app,
    container,
    push,
    apiGet,
    reserve,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
  document.body.innerHTML = ''
})

describe('TicketPurchasePage', () => {
  it('prefills event and seat category from query when values match loaded data', async () => {
    const { app, container } = await mountPage({
      reserveError: new Error('reserve should not run during prefill test'),
      waitlistState: null,
      routeQuery: {
        eventID: RICHARD_EVENT_ID,
        seatCategory: 'CAT2',
      },
      eventsPayload: [
        {
          event_id: EVENT_ID,
          event_code: 'EVT-301',
          name: 'Coldplay Live 2026',
          status: 'ACTIVE',
        },
        {
          event_id: RICHARD_EVENT_ID,
          event_code: 'EVT-501',
          name: 'Richard Boone Asia Tour 2026',
          status: 'ACTIVE',
        },
      ],
      categoriesByEventID: {
        [EVENT_ID]: [
          {
            category_id: '20000000-0000-0000-0000-000000000101',
            category_code: 'CAT1',
            name: 'Category 1',
            current_price: 88,
            currency: 'SGD',
          },
        ],
        [RICHARD_EVENT_ID]: [
          {
            category_id: '20000000-0000-0000-0000-000000000201',
            category_code: 'CAT1',
            name: 'Category 1',
            current_price: 99,
            currency: 'SGD',
          },
          {
            category_id: '20000000-0000-0000-0000-000000000202',
            category_code: 'CAT2',
            name: 'Category 2',
            current_price: 129,
            currency: 'SGD',
          },
        ],
      },
    })

    const selects = container.querySelectorAll('select')
    expect(selects[0]?.value).toBe(RICHARD_EVENT_ID)
    expect(selects[1]?.value).toBe('CAT2')

    app.unmount()
  })

  it('redirects to existing waitlist status on duplicate waitlist conflict using stored waitlist data', async () => {
    const duplicateError = {
      status: 409,
      message: 'User is already on the waitlist for this category',
    }

    const { app, container, push, apiGet } = await mountPage({
      reserveError: duplicateError,
      waitlistState: {
        waitlistID: WAITLIST_ID,
        eventID: EVENT_ID,
        seatCategory: 'CAT2',
      },
    })

    const submitButton = container.querySelector('button[type="submit"]')
    expect(submitButton).toBeTruthy()

    submitButton.click()
    await Promise.resolve()
    await Promise.resolve()

    expect(push).toHaveBeenCalledWith({
      name: 'waitlist-status',
      params: { waitlistID: WAITLIST_ID },
    })
    expect(apiGet).not.toHaveBeenCalledWith('/reserve/waitlist/my')

    app.unmount()
  })
})
