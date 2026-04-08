import { computed, ref } from 'vue'
import { HttpError } from '@/lib/httpClient'
import { formatDateTimeSGT } from '@/lib/dateTimeFormat'
import { getEvents, getPricingSnapshot } from '@/lib/scenario2Api'

function formatMoney(value, currency = 'SGD') {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null

  return new Intl.NumberFormat('en-SG', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric)
}

function formatEventDate(value) {
  return formatDateTimeSGT(value, { fallback: 'Date pending' })
}

function normalizeCatalogError(error) {
  if (error instanceof HttpError) {
    if (error.status === 0 || error.status === 408) {
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'unknown API URL'
      return `Unable to reach TicketBlitz services at ${apiBaseUrl}. Verify Kong is running and this frontend origin is allowed by CORS.`
    }

    if (error.status >= 500) {
      return 'TicketBlitz services are currently unavailable. Please try again shortly.'
    }

    return error.message || 'Unable to load events.'
  }

  return error?.message || 'Unable to load events.'
}

async function loadPricingByEvent(eventRows) {
  const pricingResults = await Promise.allSettled(
    eventRows.map((row) => getPricingSnapshot(row.event_id))
  )

  const pricingByEventID = new Map()
  pricingResults.forEach((result, index) => {
    const eventID = eventRows[index]?.event_id
    if (!eventID || result.status !== 'fulfilled') return

    const payload = result.value
    const categories = Array.isArray(payload?.categories) ? payload.categories : []
    const prices = categories
      .map((category) => Number(category?.currentPrice))
      .filter((price) => Number.isFinite(price))

    const minPrice = prices.length > 0 ? Math.min(...prices) : null
    const maxPrice = prices.length > 0 ? Math.max(...prices) : null
    const soldOutCount = categories.filter((category) => category?.status === 'SOLD_OUT').length

    pricingByEventID.set(eventID, {
      flashSaleActive: Boolean(payload?.flashSaleActive),
      flashSaleID: payload?.flashSaleID || null,
      minPrice,
      maxPrice,
      categoryCount: categories.length,
      soldOutCount,
    })
  })

  return pricingByEventID
}

export function useFanEventCatalog() {
  const events = ref([])
  const loading = ref(false)
  const refreshing = ref(false)
  const errorMessage = ref('')

  async function loadCatalog({ silent = false } = {}) {
    if (!silent) {
      loading.value = true
      errorMessage.value = ''
    } else {
      refreshing.value = true
    }

    try {
      const eventRows = await getEvents()
      const pricingByEventID = await loadPricingByEvent(eventRows)

      events.value = eventRows
        .map((eventRow) => {
          const pricing = pricingByEventID.get(eventRow.event_id) || {}

          return {
            id: eventRow.event_id,
            code: eventRow.event_code,
            name: eventRow.name,
            venue: eventRow.venue || 'Venue pending',
            eventStatus: eventRow.status || 'UNKNOWN',
            eventDate: eventRow.event_date,
            eventDateLabel: formatEventDate(eventRow.event_date),
            flashSaleActive: Boolean(pricing.flashSaleActive),
            flashSaleID: pricing.flashSaleID || null,
            categoryCount: pricing.categoryCount ?? 0,
            soldOutCount: pricing.soldOutCount ?? 0,
            minPrice: formatMoney(pricing.minPrice),
            maxPrice: formatMoney(pricing.maxPrice),
          }
        })
        .sort((a, b) => {
          const first = a.eventDate ? new Date(a.eventDate).getTime() : Number.POSITIVE_INFINITY
          const second = b.eventDate ? new Date(b.eventDate).getTime() : Number.POSITIVE_INFINITY
          return first - second
        })
    } catch (error) {
      errorMessage.value = normalizeCatalogError(error)
      events.value = []
    } finally {
      loading.value = false
      refreshing.value = false
    }
  }

  const activeFlashSaleCount = computed(
    () => events.value.filter((eventRow) => eventRow.flashSaleActive).length
  )

  const totalEventCount = computed(() => events.value.length)

  const catalogMetrics = computed(() => [
    { label: 'Listed Events', value: String(totalEventCount.value) },
    { label: 'Live Flash Sales', value: String(activeFlashSaleCount.value) },
    {
      label: 'Upcoming Windows',
      value: String(events.value.filter((eventRow) => eventRow.eventStatus === 'SCHEDULED').length),
    },
  ])

  void loadCatalog()

  return {
    events,
    loading,
    refreshing,
    errorMessage,
    totalEventCount,
    activeFlashSaleCount,
    catalogMetrics,
    loadCatalog,
  }
}
