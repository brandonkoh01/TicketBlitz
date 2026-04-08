import { computed, ref, watch } from 'vue'
import { buildCorrelationId, HttpError } from '@/lib/httpClient'
import { formatDateTimeSGT } from '@/lib/dateTimeFormat'
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
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'unknown API URL'
      return `Unable to reach TicketBlitz services at ${apiBaseUrl}. Verify Kong is running and this frontend origin is allowed by CORS.`
    }

    if (error.status >= 500) {
      return 'A backend dependency is currently unavailable. Please retry shortly.'
    }

    return error.message
  }

  return error?.message || 'Unexpected error. Please try again.'
}

function toCount(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  return Math.max(0, Math.floor(numeric))
}

function buildBroadcastNotice({ response, fallbackMessage }) {
  const waitlistCount = toCount(response?.waitlistCount)
  const published = response?.broadcastPublished === true

  if (waitlistCount === null) {
    return fallbackMessage
  }

  if (waitlistCount === 0) {
    if (published) {
      return `${fallbackMessage} Broadcast published, but there are no waitlisted fans for this event.`
    }

    return `${fallbackMessage} No waitlisted fans were targeted and no broadcast was published.`
  }

  if (published) {
    return `${fallbackMessage} Broadcast published for ${waitlistCount} waitlisted fan${waitlistCount === 1 ? '' : 's'}.`
  }

  const eligibilityVerb = waitlistCount === 1 ? 'was' : 'were'
  return `${fallbackMessage} Broadcast was not published even though ${waitlistCount} waitlisted fan${waitlistCount === 1 ? '' : 's'} ${eligibilityVerb} eligible.`
}

function fallbackEventLabel(value) {
  const normalized = String(value || '').trim()
  return normalized || 'your selected event'
}

function normalizeCapacityMetrics(category) {
  const availableRaw =
    category?.availableSeats ??
    category?.available_seats ??
    category?.available
  const soldRaw =
    category?.soldSeats ??
    category?.sold_seats ??
    category?.sold
  const totalRaw =
    category?.totalSeats ??
    category?.total_seats

  let availableSeats = toCount(availableRaw)
  let soldSeats = toCount(soldRaw)

  const hasAvailable = availableSeats !== null
  const hasSold = soldSeats !== null

  if (!hasAvailable) availableSeats = 0
  if (!hasSold) soldSeats = 0

  let totalSeats = toCount(totalRaw)
  if (totalSeats === null) {
    const inferredTotal = availableSeats + soldSeats
    totalSeats = inferredTotal > 0 ? inferredTotal : 0
  }

  if (!hasAvailable && hasSold && totalSeats > 0) {
    availableSeats = Math.max(totalSeats - soldSeats, 0)
  }

  if (!hasSold && hasAvailable && totalSeats > 0) {
    soldSeats = Math.max(totalSeats - availableSeats, 0)
  }

  const observedTotal = availableSeats + soldSeats
  if (observedTotal > totalSeats) {
    totalSeats = observedTotal
  }

  if (!hasSold && category?.status === 'SOLD_OUT' && totalSeats > 0) {
    soldSeats = totalSeats
    availableSeats = 0
  }

  const clampedAvailable = Math.max(Math.min(availableSeats, totalSeats), 0)
  const clampedSold = Math.max(Math.min(soldSeats, totalSeats), 0)

  const soldPercent = totalSeats > 0
    ? Math.round((clampedSold / totalSeats) * 100)
    : (category?.status === 'SOLD_OUT' ? 100 : 0)

  return {
    availableSeats: clampedAvailable,
    soldSeats: clampedSold,
    totalSeats,
    soldPercent,
  }
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

  function mapCategoryProgressClass(category, isChanged) {
    if (category.status === 'SOLD_OUT') {
      return 'bg-rose-300'
    }

    if (isChanged) {
      return 'bg-[#ffd900]'
    }

    return 'bg-slate-300'
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
      const eventName = fallbackEventLabel(response?.eventName || selectedEventName.value)
      const expiresAtLabel = formatDateTimeSGT(response?.expiresAt, { fallback: 'N/A' })
      const fallbackMessage = `Flash sale launched for ${eventName}. Expires at ${expiresAtLabel}.`
      noticeMessage.value = buildBroadcastNotice({
        response,
        fallbackMessage,
      })

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
      const eventName = fallbackEventLabel(response?.eventName || selectedEventName.value)
      noticeMessage.value = buildBroadcastNotice({
        response,
        fallbackMessage: `Flash sale ended for ${eventName}. Standard pricing has been restored for available categories.`,
      })

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

  const selectedEventName = computed(() => {
    const selected = events.value.find((eventRow) => eventRow.event_id === selectedEventID.value)
    return fallbackEventLabel(selected?.name)
  })

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
      const { availableSeats, soldSeats, totalSeats, soldPercent } = normalizeCapacityMetrics(category)

      return {
        id: category.categoryID,
        name: category.category || category.name,
        subtitle: category.name,
        range: totalSeats > 0 ? `${availableSeats} left / ${totalSeats} seats` : `${availableSeats} left`,
        progressClass: mapCategoryProgressClass(category, changed),
        progressPercent: soldPercent,
        availableSeats,
        soldSeats,
        totalSeats,
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
