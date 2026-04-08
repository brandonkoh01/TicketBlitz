import { computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'

export function useRoleNavigation() {
  const authStore = useAuthStore()

  const roleHomePath = computed(() => authStore.roleHomePath.value)
  const dashboardPath = computed(() => roleHomePath.value)
  const isFan = computed(() => authStore.isFan.value)
  const isOrganiser = computed(() => authStore.isOrganiser.value)
  const dashboardLabel = computed(() => (isOrganiser.value ? 'Dashboard' : 'My Tickets'))
  const primaryNavItems = computed(() => {
    if (isOrganiser.value) {
      return [
        { label: 'Events', to: '/events' },
        { label: dashboardLabel.value, to: dashboardPath.value },
      ]
    }

    return [
      { label: 'Events', to: '/events' },
      { label: 'Waitlist', to: '/waitlist' },
      { label: dashboardLabel.value, to: dashboardPath.value },
    ]
  })

  return {
    dashboardPath,
    dashboardLabel,
    primaryNavItems,
    roleHomePath,
    isFan,
    isOrganiser,
  }
}
