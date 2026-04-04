import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadComposable({ roleHomePath, isFan, isOrganiser }) {
  vi.resetModules()

  vi.doMock('@/stores/authStore', () => ({
    useAuthStore: () => ({
      roleHomePath: { value: roleHomePath },
      isFan: { value: isFan },
      isOrganiser: { value: isOrganiser },
    }),
  }))

  const { useRoleNavigation } = await import('./useRoleNavigation.js')
  return useRoleNavigation()
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
})

describe('useRoleNavigation', () => {
  it('shows Dashboard and organiser dashboard path for organisers', async () => {
    const navigation = await loadComposable({
      roleHomePath: '/organiser-dashboard',
      isFan: false,
      isOrganiser: true,
    })

    expect(navigation.dashboardLabel.value).toBe('Dashboard')
    expect(navigation.dashboardPath.value).toBe('/organiser-dashboard')
    expect(navigation.primaryNavItems.value[2]).toEqual({
      label: 'Dashboard',
      to: '/organiser-dashboard',
    })
  })

  it('shows My Tickets and fan dashboard path for fans', async () => {
    const navigation = await loadComposable({
      roleHomePath: '/my-tickets',
      isFan: true,
      isOrganiser: false,
    })

    expect(navigation.dashboardLabel.value).toBe('My Tickets')
    expect(navigation.dashboardPath.value).toBe('/my-tickets')
    expect(navigation.primaryNavItems.value[2]).toEqual({
      label: 'My Tickets',
      to: '/my-tickets',
    })
  })
})