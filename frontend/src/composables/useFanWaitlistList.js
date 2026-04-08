import { computed, ref } from 'vue'
import { useApiClient } from '@/composables/useApiClient'

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

function normalizeEntry(row) {
  const status = String(row?.status || '').toUpperCase()

  return {
    waitlistID: row?.waitlistID || '',
    eventID: row?.eventID || '',
    holdID: row?.holdID || null,
    status,
    position: Number.isFinite(Number(row?.position)) ? Number(row.position) : null,
    seatCategory: row?.seatCategory || 'Unknown',
    joinedAt: row?.joinedAt || null,
    offeredAt: row?.offeredAt || null,
    joinedAtLabel: formatDateTime(row?.joinedAt),
    offeredAtLabel: formatDateTime(row?.offeredAt),
    eventName: row?.eventName || 'Unknown Event',
    eventCode: row?.eventCode || 'N/A',
    venue: row?.venue || 'Venue pending',
    eventDate: row?.eventDate || null,
    eventDateLabel: formatDateTime(row?.eventDate),
    isOfferReady: status === 'HOLD_OFFERED' && typeof row?.holdID === 'string' && row.holdID.trim().length > 0,
  }
}

export function useFanWaitlistList() {
  const api = useApiClient()

  const entries = ref([])
  const loading = ref(false)
  const refreshing = ref(false)
  const errorMessage = ref('')

  async function loadWaitlist({ silent = false } = {}) {
    if (silent) {
      refreshing.value = true
    } else {
      loading.value = true
      errorMessage.value = ''
    }

    try {
      const payload = await api.get('/reserve/waitlist/my')
      const rows = Array.isArray(payload?.entries) ? payload.entries : []
      entries.value = rows.map(normalizeEntry)
    } catch (error) {
      entries.value = []
      errorMessage.value = error?.message || 'Unable to load waitlist entries.'
    } finally {
      loading.value = false
      refreshing.value = false
    }
  }

  const waitlistMetrics = computed(() => {
    const offerCount = entries.value.filter((entry) => entry.status === 'HOLD_OFFERED').length
    const waitingCount = entries.value.filter((entry) => entry.status === 'WAITING').length

    return [
      { label: 'Active Entries', value: String(entries.value.length) },
      { label: 'Offers Ready', value: String(offerCount) },
      { label: 'Still Waiting', value: String(waitingCount) },
    ]
  })

  void loadWaitlist()

  return {
    entries,
    loading,
    refreshing,
    errorMessage,
    waitlistMetrics,
    loadWaitlist,
  }
}
