import { computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'

export function useRoleNavigation() {
  const authStore = useAuthStore()

  const roleHomePath = computed(() => authStore.roleHomePath.value)
  const dashboardPath = computed(() => roleHomePath.value)
  const isFan = computed(() => authStore.isFan.value)
  const isOrganiser = computed(() => authStore.isOrganiser.value)

  return {
    dashboardPath,
    roleHomePath,
    isFan,
    isOrganiser,
  }
}
