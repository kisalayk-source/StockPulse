import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('frontend logging', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200 }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('queues error events and flushes them to /logs/client', async () => {
    const { appLog, flushLogs } = await import('./logging')
    appLog.error('unit_test_error', { panel: 'agent' }, new Error('boom'))
    await flushLogs()

    expect(fetch).toHaveBeenCalled()
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(String(url)).toContain('/logs/client')
    expect(init.method).toBe('POST')
    const body = JSON.parse(init.body as string)
    expect(body.events).toHaveLength(1)
    expect(body.events[0].level).toBe('error')
    expect(body.events[0].message).toBe('unit_test_error')
    expect(body.events[0].context).toEqual({ panel: 'agent' })
    expect(body.events[0].stack).toMatch(/boom/)
  })

  it('attaches last request id when flushing', async () => {
    const { appLog, flushLogs, setLastRequestId } = await import('./logging')
    setLastRequestId('req-correlation-1')
    appLog.info('correlated')
    await flushLogs()

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(init.headers['X-Request-ID']).toBe('req-correlation-1')
    const body = JSON.parse(init.body as string)
    expect(body.events[0].request_id).toBe('req-correlation-1')
  })
})
