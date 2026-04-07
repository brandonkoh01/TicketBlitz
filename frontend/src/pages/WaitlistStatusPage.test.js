import { afterEach, describe, expect, it, vi } from 'vitest'

const WAITLIST_ID = '791293dd-b5d9-4bc8-b159-14f6b6161870'

async function mountPage(waitlistPayload) {
  vi.resetModules()

  const start = vi.fn()
  const replace = vi.fn()

  vi.doMock('vue-router', () => {
    return {
      useRoute: () => ({ params: { waitlistID: WAITLIST_ID } }),
      useRouter: () => ({ replace }),
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

  vi.doMock('@/composables/useWaitlistTracking', async () => {
    const { ref } = await import('vue')

    return {
      useWaitlistTracking: () => ({
        waitlist: ref(waitlistPayload),
        errorMessage: ref(''),
        start,
      }),
    }
  })

  const { createApp, nextTick } = await import('vue')
  const { default: WaitlistStatusPage } = await import('./WaitlistStatusPage.vue')

  const container = document.createElement('div')
  document.body.appendChild(container)

  const app = createApp(WaitlistStatusPage)
  app.component('SectionLabel', {
    props: {
      index: { type: String, default: '' },
      label: { type: String, default: '' },
    },
    template: '<div data-test="section-label" />',
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
    start,
    replace,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
  document.body.innerHTML = ''
})

describe('WaitlistStatusPage', () => {
  it('renders queue position and seat category from waitlist payload', async () => {
    const { app, container, start } = await mountPage({
      waitlistID: WAITLIST_ID,
      status: 'WAITING',
      position: 4,
      seatCategory: 'CAT2',
    })

    expect(start).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain('WAITING')
    expect(container.textContent).toContain('4')
    expect(container.textContent).toContain('CAT2')

    app.unmount()
  })
})
