import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('live trading safeguard', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  })

  afterEach(() => vi.unstubAllGlobals())

  it('does not enable live mode until LIVE is typed exactly', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Live' }))
    const confirmation = screen.getByRole('button', { name: /enable live mode/i })
    expect(confirmation).toBeDisabled()
    await user.type(screen.getByLabelText(/type live to continue/i), 'live')
    expect(confirmation).toBeDisabled()
    await user.clear(screen.getByLabelText(/type live to continue/i))
    await user.type(screen.getByLabelText(/type live to continue/i), 'LIVE')
    expect(confirmation).toBeEnabled()
    await user.click(confirmation)
    expect(screen.getByText(/LIVE TRADING — REAL FUNDS AT RISK/)).toBeInTheDocument()
  })

  it('renders the manual-only execution boundary', () => {
    render(<App />)
    expect(screen.getByText(/Manual orders only/i)).toBeInTheDocument()
    expect(screen.getByText(/never trigger orders/i)).toBeInTheDocument()
  })

  it('shows a market open or closed status light', () => {
    render(<App />)
    expect(screen.getByRole('status', { name: /market/i })).toBeInTheDocument()
    expect(document.querySelector('.traffic-housing')).toBeTruthy()
    expect(document.querySelectorAll('.traffic-lamp')).toHaveLength(3)
  })

  it('shows every search match in a scrollable list', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo) => {
      if (String(input).includes('/symbols/search')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            results: Array.from({ length: 12 }, (_, index) => ({
              symbol: `T${index}`,
              name: `Ticker ${index}`,
              exchange: 'NASDAQ',
            })),
          }),
        } as Response)
      }
      return Promise.reject(new Error('offline'))
    }))

    render(<App />)
    await user.type(screen.getByLabelText('Search stocks'), 'te')
    expect(await screen.findByText('T11')).toBeInTheDocument()
    expect(document.querySelector('.search-results')).toBeTruthy()
  })

  it('updates the news section to the selected stock', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/symbols/search')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            results: [{ symbol: 'META', name: 'Meta Platforms', exchange: 'NASDAQ' }],
          }),
        } as Response)
      }
      if (url.includes('/overview')) {
        const symbol = url.includes('META') ? 'META' : 'SPY'
        return Promise.resolve({
          ok: true,
          json: async () => ({
            symbol,
            current_price: 100,
            timestamp: '2026-08-12T18:00:00Z',
            session: 'regular',
            daily: {},
            previous_daily: {},
            fundamentals: {},
            news: [{
              id: `${symbol}-1`,
              headline: `${symbol} earnings beat`,
              source: 'Reuters',
              url: `https://example.com/${symbol}`,
              created_at: '2026-08-12T17:00:00Z',
            }],
          }),
        } as Response)
      }
      if (url.includes('/bars')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ symbol: 'SPY', timeframe: '1Day', bars: [] }),
        } as Response)
      }
      return Promise.reject(new Error('offline'))
    }))

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'SPY news' })).toBeInTheDocument()
    expect(await screen.findByText('SPY earnings beat')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Search stocks'), 'meta')
    await user.click(await screen.findByRole('option', { name: /Meta Platforms/i }))
    expect(await screen.findByRole('heading', { name: 'META news' })).toBeInTheDocument()
    expect(await screen.findByText('META earnings beat')).toBeInTheDocument()
  })

  it('borders news cards green for positive and red for negative', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/overview')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            symbol: 'SPY',
            current_price: 100,
            timestamp: '2026-08-12T18:00:00Z',
            session: 'regular',
            daily: {},
            previous_daily: {},
            fundamentals: {},
            news: [
              {
                id: 'up-1',
                headline: 'SPY earnings beat',
                source: 'Reuters',
                url: 'https://example.com/beat',
                created_at: '2026-08-12T17:00:00Z',
                sentiment: 'positive',
              },
              {
                id: 'down-1',
                headline: 'SPY faces lawsuit',
                source: 'Reuters',
                url: 'https://example.com/lawsuit',
                created_at: '2026-08-12T16:00:00Z',
                sentiment: 'negative',
              },
            ],
          }),
        } as Response)
      }
      if (url.includes('/bars') || url.includes('/forecast')) {
        return Promise.resolve({
          ok: true,
          json: async () => (url.includes('/bars')
            ? { symbol: 'SPY', timeframe: '1Day', bars: [] }
            : { symbol: 'SPY', forecast: [] }),
        } as Response)
      }
      return Promise.reject(new Error('offline'))
    }))

    render(<App />)
    expect(await screen.findByRole('link', { name: /SPY earnings beat/ })).toHaveClass('positive')
    expect(screen.getByRole('link', { name: /SPY faces lawsuit/ })).toHaveClass('negative')
  })

  it('shows public and investors sentiment badges beside the ticker', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/overview')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            symbol: 'SPY',
            name: 'SPDR S&P 500 ETF Trust',
            current_price: 500,
            timestamp: '2026-08-12T18:00:00Z',
            session: 'regular',
            daily: {},
            previous_daily: {},
            fundamentals: {},
            news: [],
            public_sentiment: {
              label: 'bullish',
              bullish_percent: 0.7,
              bearish_percent: 0.2,
              score: 0.6,
            },
          }),
        } as Response)
      }
      if (url.includes('/forecast') && init?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            symbol: 'SPY',
            as_of: '2026-08-12T18:00:00Z',
            model: { id: 'Kronos' },
            trend: { direction: 'down', forecast_change: -0.01 },
            forecast: [],
          }),
        } as Response)
      }
      if (url.includes('/bars')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ symbol: 'SPY', timeframe: '1Day', bars: [] }),
        } as Response)
      }
      return Promise.reject(new Error('offline'))
    }))

    render(<App />)
    expect(await screen.findByRole('heading', { name: 'SPY' })).toBeInTheDocument()
    expect(await screen.findByLabelText('Public bullish')).toBeInTheDocument()
    expect(await screen.findByLabelText('Investors bearish')).toBeInTheDocument()
  })

  it('shows an em dash when public sentiment is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/overview')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            symbol: 'SPY',
            name: 'SPDR S&P 500 ETF Trust',
            current_price: 500,
            timestamp: '2026-08-12T18:00:00Z',
            session: 'regular',
            daily: {},
            previous_daily: {},
            fundamentals: {},
            news: [],
            public_sentiment: null,
          }),
        } as Response)
      }
      if (url.includes('/bars') || url.includes('/forecast')) {
        return Promise.resolve({
          ok: true,
          json: async () => (url.includes('/bars')
            ? { symbol: 'SPY', timeframe: '1Day', bars: [] }
            : { symbol: 'SPY', forecast: [], trend: { direction: 'flat', forecast_change: 0 } }),
        } as Response)
      }
      return Promise.reject(new Error('offline'))
    }))

    render(<App />)
    const publicBadge = await screen.findByLabelText('Public unavailable')
    expect(publicBadge).toHaveTextContent(/Public\s*—/)
    expect(await screen.findByLabelText('Investors neutral')).toBeInTheDocument()
  })

  it('retries a throttled forecast instead of leaving the chart without a prediction', async () => {
    let forecastCalls = 0
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/overview')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            symbol: 'SPY',
            name: 'SPDR S&P 500 ETF Trust',
            current_price: 500,
            timestamp: '2026-08-12T18:00:00Z',
            session: 'regular',
            daily: {},
            previous_daily: {},
            fundamentals: {},
            news: [],
          }),
        } as Response)
      }
      if (url.includes('/forecast') && init?.method === 'POST' && !url.includes('/movers')) {
        forecastCalls += 1
        if (forecastCalls === 1) {
          return Promise.resolve(new Response(JSON.stringify({ detail: 'Rate limit exceeded' }), {
            status: 429,
            headers: { 'Retry-After': '0', 'Content-Type': 'application/json' },
          }))
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            symbol: 'SPY',
            as_of: '2026-08-12T18:00:00Z',
            model: { id: 'Kronos' },
            trend: { direction: 'down', forecast_change: -0.01 },
            forecast: [{ timestamp: '2026-08-13T13:30:00Z', close: 499 }],
          }),
        } as Response)
      }
      if (url.includes('/bars')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ symbol: 'SPY', timeframe: '1Day', bars: [] }),
        } as Response)
      }
      return Promise.reject(new Error('offline'))
    }))

    render(<App />)
    expect(await screen.findByText('SPDR S&P 500 ETF Trust')).toBeInTheDocument()
    expect(await screen.findByLabelText('Investors bearish', {}, { timeout: 4000 })).toBeInTheDocument()
    expect(screen.queryByText(/Partial data/)).not.toBeInTheDocument()
  })

  it('loads and selects both call and put contracts without losing expirations', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/options/contracts')) {
        const type = url.includes('type=put') ? 'put' : 'call'
        const marker = type === 'put' ? 'P' : 'C'
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            contracts: [
              {
                symbol: `SPY260814${marker}00500000`,
                underlying_symbol: 'SPY',
                expiration_date: '2026-08-14',
                type,
                strike_price: '500',
              },
              {
                symbol: `SPY260821${marker}00500000`,
                underlying_symbol: 'SPY',
                expiration_date: '2026-08-21',
                type,
                strike_price: '500',
              },
            ],
          }),
        } as Response)
      }
      if (url.includes('/options/chain')) {
        const marker = url.includes('type=put') ? 'P' : 'C'
        const date = url.includes('2026-08-21') ? '260821' : '260814'
        const contract = `SPY${date}${marker}00500000`
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            chain: {
              [contract]: { latest_quote: { bid_price: '1.25', ask_price: '1.3' } },
            },
          }),
        } as Response)
      }
      return Promise.reject(new Error('offline'))
    }))

    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Single-leg option' }))

    const expirationSelect = await screen.findByLabelText('Expiration')
    expect(screen.getByRole('option', { name: '2026-08-21' })).toBeInTheDocument()
    await user.selectOptions(expirationSelect, '2026-08-21')

    const contractSelect = await screen.findByLabelText('Strike / contract')
    await user.selectOptions(contractSelect, 'SPY260821C00500000')
    expect(screen.getByText('SPY260821C00500000')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Puts' }))
    await user.selectOptions(await screen.findByLabelText('Strike / contract'), 'SPY260821P00500000')
    expect(screen.getByText('SPY260821P00500000')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '2026-08-14' })).toBeInTheDocument()
  })
})
