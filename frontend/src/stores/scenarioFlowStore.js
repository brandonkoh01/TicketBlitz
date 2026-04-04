import { reactive, readonly } from 'vue'

const STORAGE_KEY = 'ticketblitz-scenario1-flow'

function getInitialState() {
  if (typeof window === 'undefined') {
    return {
      reservation: null,
      waitlist: null,
      confirmedTickets: [],
    }
  }

  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return {
        reservation: null,
        waitlist: null,
        confirmedTickets: [],
      }
    }

    const parsed = JSON.parse(raw)
    return {
      reservation: parsed?.reservation ?? null,
      waitlist: parsed?.waitlist ?? null,
      confirmedTickets: Array.isArray(parsed?.confirmedTickets) ? parsed.confirmedTickets : [],
    }
  } catch {
    return {
      reservation: null,
      waitlist: null,
      confirmedTickets: [],
    }
  }
}

const state = reactive(getInitialState())

function persist() {
  if (typeof window === 'undefined') return

  window.sessionStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      reservation: state.reservation,
      waitlist: state.waitlist,
      confirmedTickets: state.confirmedTickets,
    })
  )
}

function upsertConfirmedTicket(ticket) {
  if (!ticket || typeof ticket !== 'object') return
  const holdID = typeof ticket.holdID === 'string' ? ticket.holdID.trim() : ''
  if (!holdID) return

  const nextTicket = {
    holdID,
    ticketID: ticket.ticketID || null,
    seatNumber: ticket.seatNumber || null,
    eventName: ticket.eventName || 'TicketBlitz Event',
    status: ticket.status || 'CONFIRMED',
    issuedAt: ticket.issuedAt || null,
    updatedAt: ticket.updatedAt || new Date().toISOString(),
  }

  const index = state.confirmedTickets.findIndex((item) => item.holdID === holdID)
  if (index >= 0) {
    state.confirmedTickets[index] = {
      ...state.confirmedTickets[index],
      ...nextTicket,
    }
  } else {
    state.confirmedTickets.unshift(nextTicket)
  }

  persist()
}

function setReservation(data) {
  state.reservation = data
  persist()
}

function setWaitlist(data) {
  state.waitlist = data
  persist()
}

function clearReservation() {
  state.reservation = null
  persist()
}

function clearWaitlist() {
  state.waitlist = null
  persist()
}

function clearAll() {
  state.reservation = null
  state.waitlist = null
  state.confirmedTickets = []
  persist()
}

export function useScenarioFlowStore() {
  return {
    state: readonly(state),
    setReservation,
    setWaitlist,
    upsertConfirmedTicket,
    clearReservation,
    clearWaitlist,
    clearAll,
  }
}
