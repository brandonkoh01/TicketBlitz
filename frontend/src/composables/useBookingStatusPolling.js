import { onUnmounted, ref, unref } from 'vue'
import { useApiClient } from '@/composables/useApiClient'

const TERMINAL_STATUSES = new Set(['CONFIRMED', 'FAILED_PAYMENT', 'EXPIRED'])

export function useBookingStatusPolling(holdID, { intervalMs = 2000, onTerminal } = {}) {
  const api = useApiClient()

  const payload = ref(null)
  const isPolling = ref(false)
  const errorMessage = ref('')
  let intervalId = null

  function resolveHoldID() {
    return String(unref(holdID) || '').trim()
  }

  async function pollOnce({ reconcilePayment = false } = {}) {
    try {
      errorMessage.value = ''
      const resolvedHoldID = resolveHoldID()
      if (!resolvedHoldID) {
        errorMessage.value = 'Missing hold identifier for booking status polling.'
        return null
      }

      const query = reconcilePayment ? '?reconcilePayment=true' : ''
      const response = await api.get(`/booking-status/${resolvedHoldID}${query}`, { includeUserHeader: false })
      payload.value = response

      if (response?.holdExpiry) {
        // Keep latest payload for countdown consumers.
        payload.value.holdExpiry = response.holdExpiry
      }

      if (TERMINAL_STATUSES.has(response?.uiStatus)) {
        stop()
        if (typeof onTerminal === 'function') {
          onTerminal(response)
        }
      }

      return response
    } catch (error) {
      errorMessage.value = error?.message || 'Unable to poll booking status.'
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
    payload,
    isPolling,
    errorMessage,
    pollOnce,
    start,
    stop,
  }
}
