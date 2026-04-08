import { computed, ref, watch } from 'vue'
import { HttpError } from '@/lib/httpClient'
import { getEventById } from '@/lib/scenario2Api'
import { useFanEventCatalog } from '@/composables/useFanEventCatalog'

const UPCOMING_LIMIT = 3
const FEATURED_EVENT_CODE = 'EVT-501'
const BOOKABLE_STATUSES = new Set(['ACTIVE', 'SCHEDULED', 'FLASH_SALE_ACTIVE'])
const HERO_SHOWCASE_BANNERS = Object.freeze([
  { label: 'Global Tickets Sold', value: '2.5M+' },
  { label: 'Partner Venues', value: '120' },
  { label: 'Verified Artists', value: '500+' },
])

function isBookableStatus(status) {
  return BOOKABLE_STATUSES.has(status)
}

function toEventTimestamp(eventDate) {
  if (!eventDate) return Number.POSITIVE_INFINITY

  const parsed = new Date(eventDate).getTime()
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY
}

function isUpcomingBookable(eventRow) {
  if (!eventRow || !isBookableStatus(eventRow.eventStatus)) return false
  return toEventTimestamp(eventRow.eventDate) >= Date.now()
}

function formatCompactDate(eventDate) {
  const parsed = new Date(eventDate)
  if (Number.isNaN(parsed.getTime())) return 'Date pending'

  return new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(parsed)
}

function deriveCardStatus(eventRow) {
  if (eventRow.categoryCount > 0 && eventRow.soldOutCount >= eventRow.categoryCount) {
    return 'Sold Out'
  }

  if (eventRow.soldOutCount > 0) {
    return 'Low Stock'
  }

  return 'Available'
}

function deriveCardAction(status) {
  if (status === 'Sold Out') {
    return 'Details'
  }

  return 'Buy Now'
}

function mapEventCard(eventRow) {
  const status = deriveCardStatus(eventRow)
  const compactDate = formatCompactDate(eventRow.eventDate)

  return {
    id: eventRow.id,
    title: eventRow.name,
    dateLocation: `${compactDate} - ${eventRow.venue}`,
    price: eventRow.minPrice || eventRow.maxPrice || 'TBA',
    status,
    action: deriveCardAction(status),
    actionTo: `/events/${eventRow.id}`,
  }
}

function normalizeFeaturedError(error) {
  if (error instanceof HttpError) {
    if (error.status >= 500) {
      return 'Featured event details are temporarily unavailable.'
    }

    if (error.status === 404) {
      return 'Featured event record is unavailable.'
    }
  }

  return error?.message || 'Unable to load featured event details.'
}

function fallbackFeaturedCopy(eventRow) {
  return `Book ${eventRow.name} at ${eventRow.venue} before allocations close.`
}

export function useHomeEventShowcase() {
  const {
    events,
    loading,
    refreshing,
    errorMessage,
    loadCatalog,
  } = useFanEventCatalog()

  const featuredDescription = ref('')
  const featuredLoading = ref(false)
  const featuredErrorMessage = ref('')
  const heroBanners = computed(() => HERO_SHOWCASE_BANNERS)

  const upcomingSourceRows = computed(() => {
    return events.value
      .filter((eventRow) => isUpcomingBookable(eventRow))
      .sort((first, second) => toEventTimestamp(first.eventDate) - toEventTimestamp(second.eventDate))
      .slice(0, UPCOMING_LIMIT)
  })

  const featuredSourceEvent = computed(() => {
    const bookableEvents = events.value.filter((eventRow) => isBookableStatus(eventRow.eventStatus))
    const richardBooneEvent = bookableEvents.find((eventRow) => eventRow.code === FEATURED_EVENT_CODE)
    return richardBooneEvent || bookableEvents[0] || null
  })

  const featuredSourceEventID = computed(() => featuredSourceEvent.value?.id || null)

  watch(
    featuredSourceEventID,
    async (eventID) => {
      if (!eventID) {
        featuredDescription.value = ''
        featuredErrorMessage.value = ''
        featuredLoading.value = false
        return
      }

      featuredLoading.value = true
      featuredErrorMessage.value = ''

      try {
        const payload = await getEventById(eventID)
        const description = typeof payload?.description === 'string' ? payload.description.trim() : ''
        featuredDescription.value = description
      } catch (error) {
        featuredDescription.value = ''
        featuredErrorMessage.value = normalizeFeaturedError(error)
      } finally {
        featuredLoading.value = false
      }
    },
    { immediate: true }
  )

  const upcomingEvents = computed(() => upcomingSourceRows.value.map((eventRow) => mapEventCard(eventRow)))

  const featuredEvent = computed(() => {
    const sourceEvent = featuredSourceEvent.value
    if (!sourceEvent) return null

    return {
      id: sourceEvent.id,
      name: sourceEvent.name,
      venue: sourceEvent.venue,
      dateLabel: sourceEvent.eventDateLabel,
      copy: featuredDescription.value || fallbackFeaturedCopy(sourceEvent),
      detailTo: `/events/${sourceEvent.id}`,
    }
  })

  const loadingUpcoming = computed(() => loading.value || refreshing.value)
  const loadingFeatured = computed(() => loading.value || featuredLoading.value)

  function reloadHome() {
    featuredErrorMessage.value = ''
    void loadCatalog({ silent: false })
  }

  return {
    heroBanners,
    upcomingEvents,
    featuredEvent,
    loadingUpcoming,
    loadingFeatured,
    upcomingErrorMessage: errorMessage,
    featuredErrorMessage,
    reloadHome,
  }
}