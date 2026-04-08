import { afterEach, describe, expect, it, vi } from 'vitest'

const WAITLIST_ID = '791293dd-b5d9-4bc8-b159-14f6b6161870'

async function mountPage(waitlistPayload, { leaveResponse = { status: 'CANCELLED' } } = {}) {
  vi.resetModules()

  const start = vi.fn()
  const del = vi.fn().mockResolvedValue(leaveResponse)
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

  vi.doMock('@/composables/useApiClient', () => ({
    useApiClient: () => ({
      del,
    }),
  }))

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
  app.component('UiButton', {
    props: {
      as: { type: String, default: 'button' },
      variant: { type: String, default: 'primary' },
      disabled: { type: Boolean, default: false },
    },
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
  })
  app.mount(container)

  await nextTick()

  return {
    app,
    container,
    del,
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

  it('leaves waitlist and redirects when Leave Waitlist is clicked', async () => {
    const { app, container, del, replace } = await mountPage({
      waitlistID: WAITLIST_ID,
      status: 'WAITING',
      position: 4,
      seatCategory: 'CAT2',
    })

    const leaveButton = Array.from(container.querySelectorAll('button')).find((node) =>
      (node.textContent || '').includes('Leave Waitlist')
    )
    expect(leaveButton).toBeTruthy()

    leaveButton.click()
    await Promise.resolve()

    const confirmButton = Array.from(container.querySelectorAll('button')).find((node) =>
      (node.textContent || '').includes('Yes, Leave Waitlist')
    )
    expect(confirmButton).toBeTruthy()

    confirmButton.click()
    await Promise.resolve()

    expect(del).toHaveBeenCalledWith(`/waitlist/leave/${WAITLIST_ID}`)
    expect(replace).toHaveBeenCalledWith({ name: 'ticket-purchase' })

    app.unmount()
  })
})
