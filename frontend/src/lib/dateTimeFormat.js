function getPart(parts, type) {
  const match = parts.find((part) => part.type === type)
  return match?.value || ''
}

export function formatDateTimeSGT(value, { fallback = 'Not available' } = {}) {
  if (!value) return fallback

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return fallback

  const parts = new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore',
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).formatToParts(parsed)

  const day = getPart(parts, 'day')
  const month = getPart(parts, 'month')
  const year = getPart(parts, 'year')
  const hour = getPart(parts, 'hour')
  const minute = getPart(parts, 'minute')
  const dayPeriod = getPart(parts, 'dayPeriod').toUpperCase()

  if (!day || !month || !year || !hour || !minute || !dayPeriod) {
    return fallback
  }

  return `${day}/${month}/${year} ${hour}:${minute} ${dayPeriod} SGT`
}
