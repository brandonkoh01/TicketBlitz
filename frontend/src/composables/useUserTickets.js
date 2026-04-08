import { ref } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useApiClient } from '@/composables/useApiClient'
import { ApiClientError } from '@/lib/apiClient'

const EMPTY_RESULT_404_CODES = new Set(['TICKET_NOT_FOUND', 'USER_NOT_FOUND', 'NO_TICKETS'])

function normalizeErrorCode(error) {
  if (typeof error?.code === 'string' && error.code.trim()) {
    return error.code.trim().toUpperCase()
  }

  if (typeof error?.payload?.code === 'string' && error.payload.code.trim()) {
    return error.payload.code.trim().toUpperCase()
  }

  const nestedErrorCode = error?.payload?.error?.code
  if (typeof nestedErrorCode === 'string' && nestedErrorCode.trim()) {
    return nestedErrorCode.trim().toUpperCase()
  }

  return ''
}

function normalizeErrorText(error) {
  const parts = [
    error?.message,
    error?.payload?.message,
    typeof error?.payload?.error === 'string' ? error.payload.error : '',
    error?.payload?.details,
    error?.payload?.error?.message,
  ]

  return parts
    .filter((value) => typeof value === 'string' && value.trim())
    .map((value) => value.trim().toUpperCase())
    .join(' | ')
}

function buildTicketErrorState(error) {
  if (!(error instanceof ApiClientError)) {
    return {
      kind: 'unknown',
      status: 0,
      code: '',
      message: error?.message || 'Unable to load tickets from e-ticket service.',
    }
  }

  const status = Number(error.status || 0)
  const code = normalizeErrorCode(error)
  const detailText = normalizeErrorText(error)

  const isNoTickets404 =
    status === 404 &&
    (EMPTY_RESULT_404_CODES.has(code) ||
      detailText.includes('NO TICKET') ||
      detailText.includes('NO ETICKET') ||
      detailText.includes('NO E-TICKET') ||
      detailText.includes('USER HAS NO TICKETS'))

  if (isNoTickets404) {
    return {
      kind: 'empty',
      status,
      code: code || 'TICKET_NOT_FOUND',
      message: '',
    }
  }

  if (status === 404) {
    return {
      kind: 'endpoint-missing',
      status,
      code: code || 'ENDPOINT_NOT_FOUND',
      message: 'Please buy a ticket to see your confirmed tickets',
    }
  }

  if (status === 0 || status === 408) {
    return {
      kind: 'network',
      status,
      code,
      message: 'Unable to reach TicketBlitz services. Check connectivity and try again.',
    }
  }

  if (status >= 500) {
    return {
      kind: 'server',
      status,
      code,
      message: 'Ticket services are temporarily unavailable. Please try again shortly.',
    }
  }

  return {
    kind: 'request',
    status,
    code,
    message: error.message || 'Unable to load tickets from e-ticket service.',
  }
}

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
  const requestState = ref({
    kind: 'idle',
    status: 0,
    code: '',
    message: '',
  })

  async function fetchUserTickets() {
    errorMessage.value = ''
    requestState.value = {
      kind: 'loading',
      status: 0,
      code: '',
      message: '',
    }

    const userID = String(authStore.state.user?.id || '').trim()
    if (!userID) {
      tickets.value = []
      requestState.value = {
        kind: 'idle',
        status: 0,
        code: '',
        message: '',
      }
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

      requestState.value = {
        kind: 'success',
        status: 200,
        code: '',
        message: '',
      }

      return tickets.value
    } catch (error) {
      const normalizedError = buildTicketErrorState(error)

      if (normalizedError.kind === 'empty') {
        tickets.value = []
        requestState.value = {
          kind: 'success',
          status: 200,
          code: normalizedError.code,
          message: '',
        }
        return tickets.value
      }

      errorMessage.value = normalizedError.message
      requestState.value = normalizedError
      throw error
    } finally {
      isLoading.value = false
    }
  }

  return {
    tickets,
    isLoading,
    errorMessage,
    requestState,
    fetchUserTickets,
  }
}
