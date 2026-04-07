import { ref } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useApiClient } from '@/composables/useApiClient'

function normalizeEventID(value) {
  const parsed = String(value || '').trim()
  return parsed || null
}

function fallbackEventName(eventID) {
  if (!eventID) return 'TicketBlitz Event'
  return `Event ${eventID.slice(0, 8).toUpperCase()}`
}

function normalizeTicket(rawTicket, eventNameByID) {
  const holdID = String(rawTicket?.holdID || '').trim()
  const ticketID = String(rawTicket?.ticketID || '').trim()

  if (!holdID && !ticketID) {
    return null
  }

  const issuedAt = rawTicket?.issuedAt || null
  const updatedAt = rawTicket?.updatedAt || issuedAt || new Date().toISOString()
  const eventID = normalizeEventID(rawTicket?.eventID)
  const resolvedEventName = eventNameByID.get(eventID || '') || rawTicket?.eventName || fallbackEventName(eventID)

  return {
    holdID: holdID || null,
    ticketID: ticketID || null,
    seatNumber: rawTicket?.seatNumber || null,
    eventName: resolvedEventName,
    status: rawTicket?.status || 'CONFIRMED',
    issuedAt,
    updatedAt,
  }
}

async function fetchEventNameLookup(api, rawTickets) {
  const uniqueEventIDs = [...new Set(rawTickets.map((ticket) => normalizeEventID(ticket?.eventID)).filter(Boolean))]
  if (uniqueEventIDs.length === 0) {
    return new Map()
  }

  const results = await Promise.allSettled(
    uniqueEventIDs.map(async (eventID) => {
      const eventPayload = await api.get(`/event/${encodeURIComponent(eventID)}`, {
        includeUserHeader: false,
      })

      return {
        eventID,
        eventName: String(eventPayload?.name || '').trim(),
      }
    })
  )

  const eventNameByID = new Map()
  for (const result of results) {
    if (result.status !== 'fulfilled') continue

    const eventID = normalizeEventID(result.value?.eventID)
    const eventName = String(result.value?.eventName || '').trim()
    if (!eventID || !eventName) continue

    eventNameByID.set(eventID, eventName)
  }

  return eventNameByID
}

export function useUserTickets() {
  const authStore = useAuthStore()
  const api = useApiClient()

  const tickets = ref([])
  const isLoading = ref(false)
  const errorMessage = ref('')

  async function fetchUserTickets() {
    errorMessage.value = ''

    const userID = String(authStore.state.user?.id || '').trim()
    if (!userID) {
      tickets.value = []
      return tickets.value
    }

    isLoading.value = true
    try {
      const response = await api.get(`/etickets/user/${encodeURIComponent(userID)}`, {
        includeUserHeader: false,
      })

      const upstreamTickets = Array.isArray(response?.tickets) ? response.tickets : []
      const eventNameByID = await fetchEventNameLookup(api, upstreamTickets)

      tickets.value = upstreamTickets
        .map((ticket) => normalizeTicket(ticket, eventNameByID))
        .filter(Boolean)

      return tickets.value
    } catch (error) {
      errorMessage.value = error?.message || 'Unable to load tickets from e-ticket service.'
      throw error
    } finally {
      isLoading.value = false
    }
  }

  return {
    tickets,
    isLoading,
    errorMessage,
    fetchUserTickets,
  }
}
