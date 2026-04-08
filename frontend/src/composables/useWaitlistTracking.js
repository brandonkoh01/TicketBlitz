import { onUnmounted, ref } from 'vue'
import { useApiClient } from '@/composables/useApiClient'

const TERMINAL_WAITLIST_STATUSES = new Set(['CONFIRMED', 'EXPIRED', 'CANCELLED'])

export function useWaitlistTracking(waitlistID, { intervalMs = 5000, onOffer, onTerminal } = {}) {
  const api = useApiClient()

  const waitlist = ref(null)
  const isPolling = ref(false)
  const errorMessage = ref('')
  let intervalId = null

  async function pollOnce() {
    try {
      errorMessage.value = ''
      const response = await api.get(`/waitlist/${waitlistID}`, { includeUserHeader: false })
      waitlist.value = response

      if (response?.status === 'HOLD_OFFERED' && response?.holdID && typeof onOffer === 'function') {
        stop()
        onOffer(response)
        return response
      }

      if (TERMINAL_WAITLIST_STATUSES.has(response?.status)) {
        stop()
        if (typeof onTerminal === 'function') {
          onTerminal(response)
        }
      }

      return response
    } catch (error) {
      errorMessage.value = error?.message || 'Unable to poll waitlist status.'
      return null
    }
  }

  function start() {
    if (intervalId) return

    isPolling.value = true
    pollOnce()

    intervalId = window.setInterval(() => {
      pollOnce()
    }, intervalMs)
  }

  function stop() {
    if (!intervalId) return

    window.clearInterval(intervalId)
    intervalId = null
    isPolling.value = false
  }

  onUnmounted(() => {
    stop()
  })

  return {
    waitlist,
    isPolling,
    errorMessage,
    pollOnce,
    start,
    stop,
  }
}
