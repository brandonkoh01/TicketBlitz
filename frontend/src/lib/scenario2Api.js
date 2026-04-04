import { buildCorrelationId, isUuid, requestJson } from '@/lib/httpClient'

function ensureUuid(value, fieldName) {
  if (!isUuid(value)) {
    throw new Error(`${fieldName} must be a valid UUID.`)
  }

  return value
}

function ensureNumberInRange(value, fieldName, min, max) {
  const numeric = Number(value)

  if (!Number.isFinite(numeric) || numeric < min || numeric > max) {
    throw new Error(`${fieldName} must be between ${min} and ${max}.`)
  }

  return numeric
}

export async function getEvents() {
  const data = await requestJson('/events')
  return Array.isArray(data?.events) ? data.events : []
}

export async function getEventById(eventID) {
  const parsedEventID = ensureUuid(eventID, 'eventID')
  return requestJson(`/event/${parsedEventID}`)
}

export async function getPricingSnapshot(eventID) {
  const parsedEventID = ensureUuid(eventID, 'eventID')
  return requestJson(`/pricing/${parsedEventID}`)
}

export async function getFlashSaleStatus(eventID) {
  const parsedEventID = ensureUuid(eventID, 'eventID')
  return requestJson(`/flash-sale/${parsedEventID}/status`)
}

export async function launchFlashSale({ eventID, discountPercentage, durationMinutes, escalationPercentage, correlationID }) {
  const parsedEventID = ensureUuid(eventID, 'eventID')
  const parsedDiscount = ensureNumberInRange(discountPercentage, 'discountPercentage', 0.01, 100)
  const parsedDuration = ensureNumberInRange(durationMinutes, 'durationMinutes', 1, 40320)
  const parsedEscalation = ensureNumberInRange(escalationPercentage, 'escalationPercentage', 0, 500)

  return requestJson('/flash-sale/launch', {
    method: 'POST',
    requiresOrganiserAuth: true,
    body: {
      eventID: parsedEventID,
      discountPercentage: String(parsedDiscount),
      durationMinutes: Math.round(parsedDuration),
      escalationPercentage: String(parsedEscalation),
      correlationID: correlationID || buildCorrelationId(),
    },
  })
}

export async function endFlashSale({ eventID, flashSaleID, correlationID }) {
  const parsedEventID = ensureUuid(eventID, 'eventID')
  const parsedFlashSaleID = ensureUuid(flashSaleID, 'flashSaleID')

  return requestJson('/flash-sale/end', {
    method: 'POST',
    requiresOrganiserAuth: true,
    body: {
      eventID: parsedEventID,
      flashSaleID: parsedFlashSaleID,
      correlationID: correlationID || buildCorrelationId(),
    },
  })
}
