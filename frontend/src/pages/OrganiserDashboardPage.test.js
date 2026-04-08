import { afterEach, describe, expect, it, vi } from 'vitest'

async function mountPage({ tierRows = [] } = {}) {
  vi.resetModules()

  vi.doMock('@/stores/authStore', async () => {
    const { ref } = await import('vue')

    return {
      useAuthStore: () => ({
        isAuthenticated: ref(true),
      }),
    }
  })

  vi.doMock('@/composables/useOrganiserDashboardScenario2', async () => {
    const { ref } = await import('vue')

    return {
      useOrganiserDashboardScenario2: () => ({
        discountPercentage: ref('30'),
        durationMinutes: ref('30'),
        escalationPercentage: ref('20'),
        errorMessage: ref(''),
        noticeMessage: ref(''),
        unsupportedMessage: ref(''),
        eventsLoading: ref(false),
        launchLoading: ref(false),
        endLoading: ref(false),
        requestBusy: ref(false),
        selectedEventID: ref('10000000-0000-0000-0000-000000000301'),
        eventOptions: ref([
          {
            id: '10000000-0000-0000-0000-000000000301',
            label: 'Coldplay Live 2026',
          },
        ]),
        tierRows: ref(tierRows),
        flashSaleIsActive: ref(true),
        activeFlashSaleID: ref('ea2e16ad-b5be-4803-8ce6-05f9cb93ab20'),
        canEndFlashSale: ref(true),
        lastCorrelationID: ref(''),
        systemHealth: ref({
          activeSessions: '1 Event',
          progressPercent: 78,
          insight: 'Flash sale is active.',
        }),
        clearFlashMessages: vi.fn(),
        loadEvents: vi.fn(),
        launchSelectedFlashSale: vi.fn(),
        endSelectedFlashSale: vi.fn(),
      }),
    }
  })

  const { createApp, nextTick } = await import('vue')
  const { default: OrganiserDashboardPage } = await import('./OrganiserDashboardPage.vue')

  const container = document.createElement('div')
  document.body.appendChild(container)

  const app = createApp(OrganiserDashboardPage)
  app.component('RouterLink', {
    props: {
      to: {
        type: [String, Object],
        default: '',
      },
    },
    template: '<a :href="typeof to === \'string\' ? to : \'#\'"><slot /></a>',
  })
  app.component('AuthSessionControls', {
    template: '<div data-test="auth-controls" />',
  })
  app.component('UiMaterialIcon', {
    props: {
      name: {
        type: String,
        default: '',
      },
    },
    template: '<span>{{ name }}</span>',
  })
  app.component('UiDashboardPanel', {
    template: '<section><slot /></section>',
  })
  app.component('UiToggleSwitch', {
    template: '<div data-test="toggle" />',
  })

  app.mount(container)
  await nextTick()

  return {
    app,
    container,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
  document.body.innerHTML = ''
})

describe('OrganiserDashboardPage', () => {
  it('removes Actions column and wires Events links to /events', async () => {
    const { app, container } = await mountPage({
      tierRows: [
        {
          id: '30000000-0000-0000-0000-000000000001',
          name: 'CAT1',
          subtitle: 'Category 1',
          range: '10 left / 40 seats',
          progressClass: 'bg-slate-300',
          progressPercent: 75,
          soldSeats: 30,
          price: '$120.00',
          status: 'active',
          isChanged: false,
        },
      ],
    })

    expect(container.textContent).not.toContain('Actions')
    expect(container.textContent).toContain('10 left / 40 seats')
    expect(container.textContent).toContain('Sold 30')

    const eventsLinks = Array.from(container.querySelectorAll('a[href="/events"]'))
    expect(eventsLinks.length).toBeGreaterThanOrEqual(1)

    const eventsMentions = (container.textContent || '').match(/Events/g) || []
    expect(eventsMentions.length).toBeGreaterThanOrEqual(2)

    app.unmount()
  })
})
