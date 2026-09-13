/**
 * Frontend logger — console + batched POST to /api/v1/logs/client (→ Elastic when enabled).
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface LogContext {
  [key: string]: unknown
}

type QueuedEvent = {
  level: LogLevel
  message: string
  context?: LogContext
  stack?: string
  request_id?: string
  path?: string
  user_agent?: string
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
const API_KEY = import.meta.env.VITE_API_KEY || ''

const queue: QueuedEvent[] = []
let flushTimer: number | null = null
let lastRequestId: string | null = null

function getAccessToken(): string | null {
  try {
    return localStorage.getItem('stockpulse_access_token')
  } catch {
    return null
  }
}

export function setLastRequestId(id: string | null) {
  lastRequestId = id
}

export function getLastRequestId(): string | null {
  return lastRequestId
}

function enqueue(event: QueuedEvent) {
  queue.push({
    ...event,
    request_id: event.request_id || lastRequestId || undefined,
    path: event.path || (typeof window !== 'undefined' ? window.location.pathname : undefined),
    user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
  })
  if (queue.length >= 20) {
    void flushLogs()
    return
  }
  if (flushTimer == null && typeof window !== 'undefined') {
    flushTimer = window.setTimeout(() => {
      flushTimer = null
      void flushLogs()
    }, 2000)
  }
}

export async function flushLogs(): Promise<void> {
  if (queue.length === 0) return
  const batch = queue.splice(0, queue.length)
  try {
    const token = getAccessToken()
    await fetch(`${API_BASE}/logs/client`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(lastRequestId ? { 'X-Request-ID': lastRequestId } : {}),
      },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
    })
  } catch {
    if (batch.length <= 50) queue.unshift(...batch.slice(0, 20))
  }
}

function writeConsole(level: LogLevel, message: string, context?: LogContext, stack?: string) {
  const payload = context && Object.keys(context).length ? context : undefined
  if (level === 'error') {
    console.error(message, payload || '', stack || '')
  } else if (level === 'warn') {
    console.warn(message, payload || '')
  } else if (level === 'debug') {
    console.debug(message, payload || '')
  } else {
    console.info(message, payload || '')
  }
}

export const appLog = {
  debug(message: string, context?: LogContext) {
    writeConsole('debug', message, context)
    enqueue({ level: 'debug', message, context })
  },
  info(message: string, context?: LogContext) {
    writeConsole('info', message, context)
    enqueue({ level: 'info', message, context })
  },
  warn(message: string, context?: LogContext) {
    writeConsole('warn', message, context)
    enqueue({ level: 'warn', message, context })
  },
  error(message: string, context?: LogContext, error?: unknown) {
    const stack =
      error instanceof Error
        ? error.stack || error.message
        : typeof error === 'string'
          ? error
          : undefined
    writeConsole('error', message, context, stack)
    enqueue({ level: 'error', message, context, stack })
  },
}

if (typeof window !== 'undefined') {
  window.addEventListener('error', (event) => {
    appLog.error(event.message || 'window.error', { filename: event.filename, lineno: event.lineno }, event.error)
  })
  window.addEventListener('unhandledrejection', (event) => {
    appLog.error('unhandledrejection', {}, event.reason)
  })
  window.addEventListener('beforeunload', () => {
    void flushLogs()
  })
}
