import { computed, ref } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useApiClient } from '@/composables/useApiClient'
import { useScenarioFlowStore } from '@/stores/scenarioFlowStore'

const PAYMENT_PENDING = 'PAYMENT_PENDING'
const WAITLISTED = 'WAITLISTED'
const CONFIRMED = 'CONFIRMED'

export function useScenarioReservation() {
  const authStore = useAuthStore()
  const flowStore = useScenarioFlowStore()
  const api = useApiClient()

  const isSubmitting = computed(() => api.isLoading.value)
  const errorMessage = ref('')

  function getAuthenticatedUserId() {
    const userId = authStore.state.user?.id
    if (!userId) {
      throw new Error('You are not signed in. Please sign in again.')
    }
    return userId
  }

  async function reserve({ eventID, seatCategory, qty = 1 }) {
    errorMessage.value = ''

    try {
      const userID = getAuthenticatedUserId()
      const response = await api.post('/reserve', {
        userID,
        eventID,
        seatCategory,
        qty,
      })

      if (response?.status === PAYMENT_PENDING) {
        flowStore.setReservation({
          holdID: response.holdID,
          holdExpiry: response.holdExpiry,
          amount: response.amount,
          currency: response.currency,
          paymentIntentID: response.paymentIntentID,
          clientSecret: response.clientSecret,
          returnURL: response.returnURL,
          eventID: response.eventID,
          seatCategory: response.seatCategory,
          eventName: response.eventName,
        })
        flowStore.clearWaitlist()
      }

      if (response?.status === WAITLISTED) {
        flowStore.setWaitlist({
          waitlistID: response.waitlistID,
          position: response.position,
          eventID: response.eventID,
          seatCategory: response.seatCategory,
          eventName: response.eventName,
        })
      }

      return response
    } catch (error) {
      errorMessage.value = error?.message || 'Unable to submit reservation.'
      throw error
    }
  }

  async function reserveConfirm({ holdID }) {
    errorMessage.value = ''

    try {
      const userID = getAuthenticatedUserId()
      const response = await api.post('/reserve/confirm', {
        holdID,
        userID,
      })

      if (response?.status === PAYMENT_PENDING) {
        flowStore.setReservation({
          holdID: response.holdID,
          holdExpiry: response.holdExpiry,
          amount: response.amount,
          currency: response.currency,
          paymentIntentID: response.paymentIntentID,
          clientSecret: response.clientSecret,
          paymentStatus: response.paymentStatus,
          returnURL: response.returnURL,
        })
      }

      if (response?.status === CONFIRMED) {
        flowStore.setReservation({
          holdID: response.holdID,
          paymentStatus: response.paymentStatus,
          ticket: response.ticket || null,
          status: CONFIRMED,
        })
      }

      return response
    } catch (error) {
      errorMessage.value = error?.message || 'Unable to continue reservation.'
      throw error
    }
  }

  async function fetchWaitlistConfirm(holdID) {
    errorMessage.value = ''

    try {
      return await api.get(`/waitlist/confirm/${holdID}`)
    } catch (error) {
      errorMessage.value = error?.message || 'Unable to load waitlist confirmation state.'
      throw error
    }
  }

  return {
    isSubmitting,
    errorMessage,
    reserve,
    reserveConfirm,
    fetchWaitlistConfirm,
  }
}
