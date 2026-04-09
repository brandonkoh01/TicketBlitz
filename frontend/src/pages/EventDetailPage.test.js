import { afterEach, describe, expect, it, vi } from 'vitest'

const EVENT_ID = '10000000-0000-0000-0000-000000000301'

async function mountPage({ status = 'ACTIVE', flashSaleActive = false } = {}) {
  vi.resetModules()

  const push = vi.fn()
  const refreshDetail = vi.fn()

  vi.doMock('vue-router', () => ({
    useRoute: () => ({ params: { eventID: EVENT_ID } }),
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
  }))

  vi.doMock('@/composables/useFanEventDetailScenario2', async () => {
    const { ref } = await import('vue')

    return {
      useFanEventDetailScenario2: () => ({
        eventSummary: ref({
          id: EVENT_ID,
          code: 'EVT-301',
          name: 'Coldplay Live 2026',
          venue: 'National Stadium Singapore',
          status,
          eventDateLabel: 'Mon, 01 Jun 2026, 08:00 PM',
          bookingOpenLabel: 'Mon, 01 Jan 2026, 08:00 PM',
          bookingCloseLabel: 'Mon, 01 Jun 2026, 07:30 PM',
        }),
        flashSale: ref({
          isActive: flashSaleActive,
          discountPercentage: '50',
          startsAtLabel: 'Mon, 01 Jun 2026, 09:00 AM',
          expiresAtLabel: 'Mon, 01 Jun 2026, 11:00 AM',
        }),
        categoryRows: ref([]),
        detailMetrics: ref([
          { label: 'Categories', value: '3' },
          { label: 'Sold Out', value: '1' },
          { label: 'Flash Sale', value: flashSaleActive ? 'Active' : 'Inactive' },
        ]),
        loading: ref(false),
        refreshing: ref(false),
        errorMessage: ref(''),
        refreshDetail,
      }),
    }
  })

  const { createApp, nextTick } = await import('vue')
  const { default: EventDetailPage } = await import('./EventDetailPage.vue')

  const container = document.createElement('div')
  document.body.appendChild(container)

  const app = createApp(EventDetailPage)
  app.component('AppTopNav', {
    props: {
      pageLabel: { type: String, default: '' },
    },
    template: '<header data-test="top-nav">{{ pageLabel }}</header>',
  })
  app.component('SectionLabel', {
    props: {
      index: { type: String, default: '' },
      label: { type: String, default: '' },
    },
    template: '<div data-test="section-label">{{ index }} {{ label }}</div>',
  })
  app.component('MetricCard', {
    props: {
      label: { type: String, default: '' },
      value: { type: String, default: '' },
      valueVariant: { type: String, default: 'default' },
    },
    template: '<div data-test="metric-card" :data-label="label" :data-value-variant="valueVariant">{{ label }} {{ value }}</div>',
  })
  app.component('CategoryPricingCard', {
    props: {
      category: { type: Object, required: true },
      selectable: { type: Boolean, default: false },
    },
    emits: ['select'],
    template: '<button @click="$emit(\'select\', category)">Select</button>',
  })
  app.component('FooterLinkGroup', {
    props: {
      title: { type: String, default: '' },
      links: { type: Array, default: () => [] },
    },
    template: '<div data-test="footer-links">{{ title }}</div>',
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

  return {
    app,
    container,
    push,
    refreshDetail,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
  document.body.innerHTML = ''
})

describe('EventDetailPage flash sale badge rendering', () => {
  it('hides raw FLASH_SALE_ACTIVE status text when flash sale is active', async () => {
    const { app, container } = await mountPage({
      status: 'FLASH_SALE_ACTIVE',
      flashSaleActive: true,
    })

    expect(container.textContent).toContain('Flash Sale Active')
    expect(container.textContent).toContain('Live Sale')
    expect(container.textContent).not.toContain('Live Scenario 2 Sale')
    expect(container.textContent).not.toContain('FLASH_SALE_ACTIVE')

    app.unmount()
  })

  it('shows normal status badge when flash sale is inactive', async () => {
    const { app, container } = await mountPage({
      status: 'ACTIVE',
      flashSaleActive: false,
    })

    expect(container.textContent).toContain('ACTIVE')
    expect(container.textContent).not.toContain('Flash Sale Active')

    const flashSaleMetricCard = container.querySelector('[data-test="metric-card"][data-label="Flash Sale"]')
    expect(flashSaleMetricCard?.getAttribute('data-value-variant')).toBe('compact')

    app.unmount()
  })
})
