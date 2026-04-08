import { ref } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { createApiClient } from '@/lib/apiClient'

export function useApiClient() {
  const authStore = useAuthStore()
  const isLoading = ref(false)
  const error = ref('')

  const api = createApiClient(authStore)

  async function run(handler) {
    error.value = ''
    isLoading.value = true

    try {
      return await handler()
    } catch (requestError) {
      error.value = requestError?.message || 'Request failed.'
      throw requestError
    } finally {
      isLoading.value = false
    }
  }

  return {
    isLoading,
    error,
    get: (path, options) => run(() => api.get(path, options)),
    post: (path, body, options) => run(() => api.post(path, body, options)),
    put: (path, body, options) => run(() => api.put(path, body, options)),
    patch: (path, body, options) => run(() => api.patch(path, body, options)),
    del: (path, options) => run(() => api.delete(path, options)),
  }
}
