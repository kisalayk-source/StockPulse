import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

const response = (payload: unknown) => ({
  ok: true,
  status: 200,
  json: async () => payload,
}) as Response

describe('FastAPI contract adapters', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('normalizes stock overview and news responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      symbol: 'AAPL',
      current_price: 201,
      timestamp: '2026-08-12T18:00:00Z',
      session: 'regular',
      daily: { open: 198, high: 202, low: 197, volume: 1000 },
      previous_daily: { close: 200 },
      fundamentals: {
        pe_ratio: 31,
        market_cap: 3_100_000_000_000,
        dividend_yield: 0.5,
        eps: 6.4,
      },
      news: [{
        id: 1,
        headline: 'Apple update',
        source: 'Benzinga',
        url: 'https://example.com',
        created_at: '2026-08-12T17:00:00Z',
        sentiment: 'positive',
      }],
    })))

    const result = await api.overview('AAPL')

    expect(result.quote.price).toBe(201)
    expect(result.quote.changePercent).toBe(0.005)
    expect(result.quote.marketCap).toBe(3_100_000_000_000)
    expect(result.news[0].publishedAt).toBe('2026-08-12T17:00:00Z')
    expect(result.news[0].sentiment).toBe('positive')
    expect(result.publicSentiment).toBeNull()
  })

  it('maps Finnhub public sentiment on overview', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      symbol: 'AAPL',
      current_price: 201,
      timestamp: '2026-08-12T18:00:00Z',
      session: 'regular',
      daily: {},
      previous_daily: {},
      fundamentals: {},
      news: [],
      public_sentiment: {
        label: 'bullish',
        bullish_percent: 0.72,
        bearish_percent: 0.18,
        score: 0.64,
      },
    })))

    const result = await api.overview('AAPL')
    expect(result.publicSentiment).toEqual({
      label: 'bullish',
      bullishPercent: 0.72,
      bearishPercent: 0.18,
      score: 0.64,
    })
  })

  it('unwraps nested Alpaca news payloads for the selected stock', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      symbol: 'META',
      current_price: 500,
      timestamp: '2026-08-12T18:00:00Z',
      session: 'regular',
      daily: {},
      previous_daily: {},
      fundamentals: {},
      news: {
        news: [{
          headline: 'Meta earnings',
          source: 'Reuters',
          url: 'https://example.com/meta',
          created_at: '2026-08-12T17:00:00Z',
        }],
        next_page_token: 'abc',
      },
    })))

    const result = await api.overview('META')
    expect(result.news).toHaveLength(1)
    expect(result.news[0].headline).toBe('Meta earnings')
  })

  it('maps live equity orders to backend field names and confirmation token', async () => {
    const fetch = vi.fn().mockResolvedValue(response({
      id: 'order-1',
      symbol: 'AAPL',
      side: 'buy',
      qty: '2',
      type: 'limit',
      limit_price: '200',
      status: 'new',
      submitted_at: '2026-08-12T18:00:00Z',
    }))
    vi.stubGlobal('fetch', fetch)

    const result = await api.placeEquityOrder({
      mode: 'live',
      symbol: 'AAPL',
      side: 'buy',
      quantity: 2,
      type: 'limit',
      limitPrice: 200,
      timeInForce: 'day',
    })

    const request = fetch.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(request.body))).toMatchObject({
      qty: 2,
      limit_price: 200,
      live_confirmation_token: 'LIVE',
    })
    expect(result.status).toBe('accepted')
    expect(result.quantity).toBe(2)
  })

  it('sends an explicit cancellation request in the selected mode', async () => {
    const fetch = vi.fn().mockResolvedValue(response({ id: 'order-1', status: 'cancel_requested' }))
    vi.stubGlobal('fetch', fetch)

    await api.cancelOrder('order-1', 'paper')

    expect(String(fetch.mock.calls[0][0])).toContain('/orders/order-1')
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'DELETE' })
    expect(JSON.parse(String(fetch.mock.calls[0][1].body))).toEqual({ mode: 'paper' })
  })

  it('maps the market clock payload', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      is_open: false,
      session: 'closed',
      timestamp: '2026-08-12T22:00:00Z',
      next_open: '2026-08-13T13:30:00Z',
      next_close: '2026-08-13T20:00:00Z',
    })))

    const result = await api.clock()
    expect(result).toEqual({
      isOpen: false,
      session: 'closed',
      timestamp: '2026-08-12T22:00:00Z',
      nextOpen: '2026-08-13T13:30:00Z',
      nextClose: '2026-08-13T20:00:00Z',
    })
  })

  it('exposes the Kronos prediction date range', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      symbol: 'AAPL',
      as_of: '2026-08-12T20:00:00Z',
      model: { id: 'NeoQuasar/Kronos-small' },
      trend: { direction: 'down', forecast_change: -0.012, net_forecast_change: -0.008 },
      costs: { round_trip_bps: 8.2 },
      regime: { label: 'high_vol_down', vol: 'high', trend: 'down' },
      evaluation: { folds: 3, hit_rate: 0.33, mean_net_return: -0.01, edge_reliable: false },
      forecast: [
        { timestamp: '2026-08-13T13:30:00Z', close: 302, lower: 298, upper: 306 },
        { timestamp: '2026-08-13T13:35:00Z', close: 303 },
      ],
    })))

    const result = await api.forecast('AAPL', 'short')

    expect(result.generatedAt).toBe('2026-08-12T20:00:00Z')
    expect(result.predictionStart).toBe('2026-08-13T13:30:00Z')
    expect(result.predictionEnd).toBe('2026-08-13T13:35:00Z')
    expect(result.sentiment).toBe('bearish')
    expect(result.forecastChange).toBe(-0.012)
    expect(result.netForecastChange).toBe(-0.008)
    expect(result.regime).toBe('high_vol_down')
    expect(result.edgeReliable).toBe(false)
    expect(result.points[0]).toMatchObject({ lower: 298, upper: 306 })
  })

  it('uses mode, type, and expiration filters for option data', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(response({
        contracts: [
          {
            symbol: 'SPY260814P00500000',
            underlying_symbol: 'SPY',
            expiration_date: '2026-08-14',
            type: 'put',
            strike_price: '500',
          },
          {
            symbol: 'SPY260821P00500000',
            underlying_symbol: 'SPY',
            expiration_date: '2026-08-21',
            type: 'put',
            strike_price: '500',
          },
        ],
      }))
      .mockResolvedValueOnce(response({
        chain: {
          SPY260821P00500000: {
            latest_quote: { bid_price: '1.25', ask_price: '1.3' },
          },
        },
      }))
    vi.stubGlobal('fetch', fetch)

    const result = await api.optionChain('SPY', 'live', '2026-08-21', 'put')

    expect(String(fetch.mock.calls[0][0])).toContain('mode=live')
    expect(String(fetch.mock.calls[0][0])).toContain('type=put')
    expect(String(fetch.mock.calls[0][0])).not.toContain('expiration=')
    expect(String(fetch.mock.calls[1][0])).toContain('expiration=2026-08-21')
    expect(String(fetch.mock.calls[1][0])).toContain('type=put')
    expect(result.expirations).toEqual(['2026-08-14', '2026-08-21'])
    expect(result.contracts[1]).toMatchObject({
      type: 'put',
      bid: 1.25,
      ask: 1.3,
    })
  })

  it('normalizes the Kronos movers scan payload', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      as_of: '2026-08-12T18:05:00Z',
      session: 'regular',
      market_open: true,
      timeframe: '5Min',
      scanned: 2,
      cached: false,
      movers: [{
        symbol: 'NVDA',
        last_price: 120,
        predicted_price: 126,
        forecast_change: 0.05,
        direction: 'up',
        day_change: 0.02,
        volume: 80_000_000,
      }],
    })))

    const result = await api.movers(true)

    expect(result.movers[0]).toMatchObject({
      symbol: 'NVDA',
      lastPrice: 120,
      forecastChange: 0.05,
      dayChange: 0.02,
    })
    expect(result.cached).toBe(false)
  })

  it('retries a throttled forecast and coalesces in-flight requests', async () => {
    const payload = {
      symbol: 'AAPL',
      as_of: '2026-08-12T20:00:00Z',
      model: { id: 'Kronos' },
      trend: { direction: 'flat', forecast_change: 0 },
      forecast: [{ timestamp: '2026-08-13T13:30:00Z', close: 200 }],
    }
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Rate limit exceeded' }), {
        status: 429,
        headers: { 'Retry-After': '0', 'Content-Type': 'application/json' },
      }))
      .mockResolvedValue(response(payload))
    vi.stubGlobal('fetch', fetch)

    const [first, second] = await Promise.all([
      api.forecast('AAPL', 'short'),
      api.forecast('AAPL', 'short'),
    ])

    expect(first.points[0].value).toBe(200)
    expect(second.points[0].value).toBe(200)
    expect(fetch.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(fetch.mock.calls.length).toBeLessThan(4)
  })
})
