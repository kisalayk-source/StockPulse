export const formatCurrency = (value: number | null | undefined, compact = false) => {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 2,
  }).format(value)
}

export const formatNumber = (value: number | null | undefined, compact = false) => {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 2,
  }).format(value)
}

export const formatPercent = (value: number | null | undefined, alreadyPercent = true) => {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${alreadyPercent ? value.toFixed(2) : (value * 100).toFixed(2)}%`
}

export const formatDateTime = (value: string | null | undefined) => {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unavailable'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(date)
}

export type MarketSession = 'regular' | 'pre_market' | 'after_hours' | 'closed' | 'unknown'
export type MarketTone = 'open' | 'extended' | 'closed' | 'unknown'

export const marketStatusLabel = (session?: string, isOpen?: boolean) => {
  if (isOpen || session === 'regular') return 'Market Open'
  if (session === 'pre_market') return 'Pre-Market'
  if (session === 'after_hours') return 'After Hours'
  if (session === 'closed') return 'Market Closed'
  return 'Market Status'
}

export const marketStatusTone = (session?: string, isOpen?: boolean): MarketTone => {
  if (isOpen || session === 'regular') return 'open'
  if (session === 'pre_market' || session === 'after_hours') return 'extended'
  if (session === 'closed') return 'closed'
  return 'unknown'
}

export const localMarketClock = (now = new Date()) => {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(now).map((part) => [part.type, part.value]),
  )
  const minutes = Number(parts.hour) * 60 + Number(parts.minute)
  const weekend = parts.weekday === 'Sat' || parts.weekday === 'Sun'
  let session: MarketSession = 'closed'
  if (!weekend) {
    if (minutes >= 570 && minutes < 960) session = 'regular'
    else if (minutes >= 240 && minutes < 570) session = 'pre_market'
    else if (minutes >= 960 && minutes < 1200) session = 'after_hours'
  }
  return { isOpen: session === 'regular', session }
}
