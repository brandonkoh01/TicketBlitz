import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadRouterWithStore(store) {
  vi.resetModules()

  const stubComponent = {
    name: 'StubComponent',
    template: '<div />',
  }

  vi.doMock('@/pages/MainLandingPage.vue', () => ({ default: stubComponent }))
  vi.doMock('@/pages/OrganiserDashboardPage.vue', () => ({ default: stubComponent }))
  vi.doMock('@/pages/TicketPurchasePage.vue', () => ({ default: stubComponent }))
  vi.doMock('@/pages/MyTicketsPage.vue', () => ({ default: stubComponent }))
  vi.doMock('@/pages/SignInPage.vue', () => ({ default: stubComponent }))
  vi.doMock('@/pages/SignUpPage.vue', () => ({ default: stubComponent }))

  vi.doMock('@/stores/authStore', () => ({
    useAuthStore: () => store,
  }))

  const { default: router } = await import('./index.js')
  return router
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
  window.history.pushState({}, '', '/')
})

describe('router auth guards', () => {
  it('redirects protected routes to sign-in when auth is disabled', async () => {
    const store = {
      initializeAuthStore: vi.fn().mockResolvedValue(undefined),
      authEnabled: false,
      isAuthenticated: { value: false },
    }

    const router = await loadRouterWithStore(store)

    await router.push('/organiser-dashboard')
    await router.isReady()

    expect(store.initializeAuthStore).toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('sign-in')
    expect(router.currentRoute.value.query.redirect).toBe('/organiser-dashboard')
  })

  it('redirects authenticated users away from guest-only routes', async () => {
    const store = {
      initializeAuthStore: vi.fn().mockResolvedValue(undefined),
      authEnabled: true,
      isAuthenticated: { value: true },
      currentRole: { value: 'fan' },
      roleHomePath: { value: '/my-tickets' },
    }

    const router = await loadRouterWithStore(store)

    await router.push('/sign-in?redirect=/my-tickets')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('my-tickets')
  })

  it('normalizes unsafe redirect query to role home', async () => {
    const store = {
      initializeAuthStore: vi.fn().mockResolvedValue(undefined),
      authEnabled: true,
      isAuthenticated: { value: true },
      currentRole: { value: 'fan' },
      roleHomePath: { value: '/my-tickets' },
    }

    const router = await loadRouterWithStore(store)

    await router.push('/sign-in?redirect=https://evil.example')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/my-tickets')
  })

  it('redirects fan users away from organiser dashboard', async () => {
    const store = {
      initializeAuthStore: vi.fn().mockResolvedValue(undefined),
      authEnabled: true,
      isAuthenticated: { value: true },
      currentRole: { value: 'fan' },
      roleHomePath: { value: '/my-tickets' },
    }

    const router = await loadRouterWithStore(store)

    await router.push('/organiser-dashboard')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('my-tickets')
  })

  it('redirects organisers away from fan dashboard', async () => {
    const store = {
      initializeAuthStore: vi.fn().mockResolvedValue(undefined),
      authEnabled: true,
      isAuthenticated: { value: true },
      currentRole: { value: 'organiser' },
      roleHomePath: { value: '/organiser-dashboard' },
    }

    const router = await loadRouterWithStore(store)

    await router.push('/my-tickets')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('organiser-dashboard')
  })
})
