import { computed, ref, watch } from 'vue'
import { buildCorrelationId, HttpError } from '@/lib/httpClient'
import {
  endFlashSale,
  getEvents,
  getFlashSaleStatus,
  getPricingSnapshot,
  launchFlashSale,
} from '@/lib/scenario2Api'

const DEFAULT_POLL_INTERVAL_MS = 5000
const CHANGE_HIGHLIGHT_MS = 4000

function toMoney(value, currency = 'SGD') {
  const numeric = Number(value)

  if (!Number.isFinite(numeric)) {
    return '$0.00'
  }

  return new Intl.NumberFormat('en-SG', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric)
}

function normalizeDashboardError(error) {
  if (error instanceof HttpError) {
    if (error.status === 401) {
      return 'Unauthorised organiser request. Check organiser API key configuration.'
    }

    if (error.status === 409) {
      return error.message || 'Conflict detected while processing the flash sale action.'
    }

    if (error.status === 0 || error.status === 408) {
      return 'Unable to reach the API gateway. Verify Kong is running and CORS is configured for this frontend origin.'
    }

    if (error.status >= 500) {
      return 'A backend dependency is currently unavailable. Please retry shortly.'
    }

    return error.message
  }

  return error?.message || 'Unexpected error. Please try again.'
}

export function useOrganiserDashboardScenario2() {
  const events = ref([])
  const selectedEventID = ref(import.meta.env.VITE_SCENARIO2_DEFAULT_EVENT_ID || '')

  const pricingSnapshot = ref(null)
  const flashSaleStatus = ref(null)

  const eventsLoading = ref(false)
  const refreshLoading = ref(false)
  const launchLoading = ref(false)
  const endLoading = ref(false)

  const errorMessage = ref('')
  const noticeMessage = ref('')
  const unsupportedMessage = ref('')
  const lastCorrelationID = ref('')

  const discountPercentage = ref('30')
  const durationMinutes = ref('30')
  const escalationPercentage = ref('20')

  const changedCategoryIDs = ref([])
  const previousCategoryState = ref(new Map())

  async function loadEvents() {
    eventsLoading.value = true

    try {
      const rows = await getEvents()
      events.value = rows

      if (!selectedEventID.value && rows.length > 0) {
        selectedEventID.value = rows[0].event_id
      }

      if (selectedEventID.value && !rows.some((row) => row.event_id === selectedEventID.value) && rows.length > 0) {
        selectedEventID.value = rows[0].event_id
      }
    } catch (error) {
      errorMessage.value = normalizeDashboardError(error)
    } finally {
      eventsLoading.value = false
    }
  }

  function clearFlashMessages() {
    errorMessage.value = ''
    noticeMessage.value = ''
  }

  function setUnsupportedMessage(actionLabel) {
    unsupportedMessage.value = `${actionLabel} is not available in the current backend scope.`
  }

  function mapCategoryProgress(category, isChanged) {
    if (category.status === 'SOLD_OUT') {
      return 'w-full bg-rose-300'
    }

    if (isChanged) {
      return 'w-full bg-[#ffd900]'
    }

    return 'w-full bg-slate-300'
  }

  function recordCategoryChanges(categories) {
    const nextState = new Map()
    const changed = []

    categories.forEach((category) => {
      const categoryID = category.categoryID
      const current = {
        price: category.currentPrice,
        status: category.status,
      }
      const previous = previousCategoryState.value.get(categoryID)

      if (previous && (previous.price !== current.price || previous.status !== current.status)) {
        changed.push(categoryID)
      }

      nextState.set(categoryID, current)
    })

    previousCategoryState.value = nextState
    changedCategoryIDs.value = changed

    if (changed.length > 0) {
      setTimeout(() => {
        if (changedCategoryIDs.value.length > 0) {
          changedCategoryIDs.value = []
        }
      }, CHANGE_HIGHLIGHT_MS)
    }
  }

  async function refreshScenario2State({ silent = false } = {}) {
    if (!selectedEventID.value) return

    if (!silent) {
      refreshLoading.value = true
      clearFlashMessages()
    }

    try {
      const [snapshot, status] = await Promise.all([
        getPricingSnapshot(selectedEventID.value),
        getFlashSaleStatus(selectedEventID.value),
      ])

      pricingSnapshot.value = snapshot
      flashSaleStatus.value = status

      recordCategoryChanges(Array.isArray(snapshot?.categories) ? snapshot.categories : [])
    } catch (error) {
      errorMessage.value = normalizeDashboardError(error)
    } finally {
      refreshLoading.value = false
    }
  }

  async function launchSelectedFlashSale() {
    if (!selectedEventID.value) {
      errorMessage.value = 'Please select an event before launching a flash sale.'
      return
    }

    launchLoading.value = true
    clearFlashMessages()

    try {
      const correlationID = buildCorrelationId()
      const response = await launchFlashSale({
        eventID: selectedEventID.value,
        discountPercentage: discountPercentage.value,
        durationMinutes: durationMinutes.value,
        escalationPercentage: escalationPercentage.value,
        correlationID,
      })

      lastCorrelationID.value = response?.correlationID || correlationID
      noticeMessage.value = `Flash sale launched successfully. Expires at ${response?.expiresAt || 'N/A'}.`

      await refreshScenario2State({ silent: true })
    } catch (error) {
      errorMessage.value = normalizeDashboardError(error)
    } finally {
      launchLoading.value = false
    }
  }

  async function endSelectedFlashSale() {
    if (!selectedEventID.value) {
      errorMessage.value = 'Please select an event before ending a flash sale.'
      return
    }

    const flashSaleID = activeFlashSaleID.value
    if (!flashSaleID) {
      errorMessage.value = 'No active flash sale is currently available for this event.'
      return
    }

    endLoading.value = true
    clearFlashMessages()

    try {
      const correlationID = buildCorrelationId()
      const response = await endFlashSale({
        eventID: selectedEventID.value,
        flashSaleID,
        correlationID,
      })

      lastCorrelationID.value = response?.correlationID || correlationID
      noticeMessage.value = 'Flash sale ended. Standard pricing restored for available categories.'

      await refreshScenario2State({ silent: true })
    } catch (error) {
      errorMessage.value = normalizeDashboardError(error)
    } finally {
      endLoading.value = false
    }
  }

  const eventOptions = computed(() =>
    events.value.map((eventRow) => ({
      id: eventRow.event_id,
      label: eventRow.name,
    }))
  )

  const activeFlashSaleID = computed(() => {
    const pricingID = pricingSnapshot.value?.flashSaleID
    if (pricingID) return pricingID

    return flashSaleStatus.value?.pricing?.flashSaleID || null
  })

  const flashSaleIsActive = computed(() => Boolean(pricingSnapshot.value?.flashSaleActive && activeFlashSaleID.value))

  const tierRows = computed(() => {
    const categories = Array.isArray(pricingSnapshot.value?.categories) ? pricingSnapshot.value.categories : []

    return categories.map((category) => {
      const changed = changedCategoryIDs.value.includes(category.categoryID)

      return {
        id: category.categoryID,
        name: category.category || category.name,
        subtitle: category.name,
        range: category.status === 'SOLD_OUT' ? 'Sold Out' : 'Available',
        progressClass: mapCategoryProgress(category, changed),
        price: toMoney(category.currentPrice, category.currency),
        status: category.status === 'SOLD_OUT' ? 'sold_out' : flashSaleIsActive.value ? 'active' : 'pending',
        isChanged: changed,
      }
    })
  })

  const systemHealth = computed(() => ({
    activeSessions: `${events.value.length} Event${events.value.length === 1 ? '' : 's'}`,
    progressPercent: flashSaleIsActive.value ? 78 : 32,
    insight: flashSaleIsActive.value
      ? 'Flash sale is active and pricing sync is running every 5 seconds.'
      : 'Flash sale is inactive. Launch a sale to start live pricing orchestration.',
  }))

  const requestBusy = computed(() => refreshLoading.value || launchLoading.value || endLoading.value)

  const canEndFlashSale = computed(() => Boolean(flashSaleIsActive.value && activeFlashSaleID.value) && !endLoading.value)

  watch(
    selectedEventID,
    (newEventID, _oldEventID, onCleanup) => {
      if (!newEventID) return

      void refreshScenario2State()

      if (typeof window === 'undefined') return

      const intervalID = window.setInterval(() => {
        void refreshScenario2State({ silent: true })
      }, DEFAULT_POLL_INTERVAL_MS)

      onCleanup(() => {
        window.clearInterval(intervalID)
      })
    },
    { immediate: true }
  )

  void loadEvents()

  return {
    discountPercentage,
    durationMinutes,
    escalationPercentage,
    errorMessage,
    noticeMessage,
    unsupportedMessage,
    eventsLoading,
    refreshLoading,
    launchLoading,
    endLoading,
    requestBusy,
    selectedEventID,
    eventOptions,
    tierRows,
    flashSaleIsActive,
    activeFlashSaleID,
    canEndFlashSale,
    lastCorrelationID,
    systemHealth,
    setUnsupportedMessage,
    clearFlashMessages,
    loadEvents,
    refreshScenario2State,
    launchSelectedFlashSale,
    endSelectedFlashSale,
  }
}
