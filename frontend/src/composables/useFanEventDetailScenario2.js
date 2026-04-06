import { computed, ref, watch } from 'vue'
import { HttpError } from '@/lib/httpClient'
import { getEventById, getFlashSaleStatus, getPricingSnapshot } from '@/lib/scenario2Api'

const DETAIL_POLL_INTERVAL_MS = 5000

function formatMoney(value, currency = 'SGD') {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'N/A'

  return new Intl.NumberFormat('en-SG', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric)
}

function formatDateTime(value) {
  if (!value) return 'Not available'

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Not available'

  return new Intl.DateTimeFormat('en-SG', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

function normalizeDetailError(error) {
  if (error instanceof HttpError) {
    if (error.status === 404) {
      return 'Event not found. It may have been removed from the public catalog.'
    }

    if (error.status === 0 || error.status === 408) {
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'unknown API URL'
      return `Unable to reach TicketBlitz services at ${apiBaseUrl}. Verify Kong is running and this frontend origin is allowed by CORS.`
    }

    if (error.status >= 500) {
      return 'TicketBlitz services are currently unavailable. Please try again shortly.'
    }

    return error.message || 'Unable to load event details.'
  }

  return error?.message || 'Unable to load event details.'
}

export function useFanEventDetailScenario2(eventIDRef) {
  const event = ref(null)
  const pricingSnapshot = ref(null)
  const flashSaleStatus = ref(null)

  const loading = ref(false)
  const refreshing = ref(false)
  const errorMessage = ref('')

  async function refreshDetail({ silent = false } = {}) {
    if (!eventIDRef?.value) return

    if (!silent) {
      loading.value = true
      errorMessage.value = ''
    } else {
      refreshing.value = true
    }

    try {
      const [eventPayload, pricingPayload, statusPayload] = await Promise.all([
        getEventById(eventIDRef.value),
        getPricingSnapshot(eventIDRef.value),
        getFlashSaleStatus(eventIDRef.value),
      ])

      event.value = eventPayload || null
      pricingSnapshot.value = pricingPayload || null
      flashSaleStatus.value = statusPayload || null
    } catch (error) {
      errorMessage.value = normalizeDetailError(error)
      event.value = null
      pricingSnapshot.value = null
      flashSaleStatus.value = null
    } finally {
      loading.value = false
      refreshing.value = false
    }
  }

  const flashSale = computed(() => {
    const pricing = pricingSnapshot.value
    const statusPricing = flashSaleStatus.value?.pricing || null

    const isActive = Boolean(pricing?.flashSaleActive && pricing?.flashSaleID)

    return {
      isActive,
      flashSaleID: pricing?.flashSaleID || statusPricing?.flashSaleID || null,
      discountPercentage: statusPricing?.discountPercentage || null,
      escalationPercentage: statusPricing?.escalationPercentage || null,
      startsAt: statusPricing?.startsAt || null,
      expiresAt: statusPricing?.expiresAt || null,
      startsAtLabel: formatDateTime(statusPricing?.startsAt),
      expiresAtLabel: formatDateTime(statusPricing?.expiresAt),
    }
  })

  const categoryRows = computed(() => {
    const categories = Array.isArray(pricingSnapshot.value?.categories)
      ? pricingSnapshot.value.categories
      : []

    return categories.map((category) => ({
      id: category.categoryID,
      code: category.category,
      name: category.name || category.category,
      status: category.status || 'UNKNOWN',
      basePriceLabel: formatMoney(category.basePrice, category.currency),
      currentPriceLabel: formatMoney(category.currentPrice, category.currency),
      changed: Number(category.currentPrice) !== Number(category.basePrice),
    }))
  })

  const detailMetrics = computed(() => {
    const rows = categoryRows.value
    const soldOutCount = rows.filter((row) => row.status === 'SOLD_OUT').length

    return [
      { label: 'Categories', value: String(rows.length) },
      { label: 'Sold Out', value: String(soldOutCount) },
      { label: 'Flash Sale', value: flashSale.value.isActive ? 'Active' : 'Inactive' },
    ]
  })

  watch(
    eventIDRef,
    (_newValue, _oldValue, onCleanup) => {
      if (!eventIDRef?.value) return

      void refreshDetail()

      if (typeof window === 'undefined') return

      const intervalID = window.setInterval(() => {
        void refreshDetail({ silent: true })
      }, DETAIL_POLL_INTERVAL_MS)

      onCleanup(() => {
        window.clearInterval(intervalID)
      })
    },
    { immediate: true }
  )

  const eventSummary = computed(() => {
    if (!event.value) return null

    return {
      id: event.value.event_id,
      code: event.value.event_code,
      name: event.value.name,
      venue: event.value.venue || 'Venue pending',
      status: event.value.status || 'UNKNOWN',
      eventDateLabel: formatDateTime(event.value.event_date),
      bookingOpenLabel: formatDateTime(event.value.booking_opens_at),
      bookingCloseLabel: formatDateTime(event.value.booking_closes_at),
    }
  })

  return {
    event,
    eventSummary,
    pricingSnapshot,
    flashSaleStatus,
    flashSale,
    categoryRows,
    detailMetrics,
    loading,
    refreshing,
    errorMessage,
    refreshDetail,
  }
}
