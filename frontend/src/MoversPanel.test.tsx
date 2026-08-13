import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MoversPanel } from './MoversPanel'

describe('MoversPanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders ranked movers and selects a symbol', async () => {
    const onSelectSymbol = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        as_of: '2026-08-12T18:05:00Z',
        timeframe: '5Min',
        scanned: 2,
        cached: false,
        movers: [
          {
            symbol: 'NVDA',
            last_price: 120,
            predicted_price: 132,
            forecast_change: 0.1,
            direction: 'up',
            day_change: 0.03,
            volume: 50_000_000,
          },
          {
            symbol: 'F',
            last_price: 11,
            predicted_price: 10,
            forecast_change: -0.08,
            direction: 'down',
            day_change: -0.02,
            volume: 40_000_000,
          },
        ],
      }),
    } as Response))

    render(<MoversPanel onSelectSymbol={onSelectSymbol} />)

    expect(await screen.findByRole('heading', { name: /top 50 potential gainers/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Gainers' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Losers' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'NVDA' })).toBeInTheDocument()
    expect(screen.getByText('10.00%')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'NVDA' }))
    expect(onSelectSymbol).toHaveBeenCalledWith('NVDA')
  })

  it('refreshes the scan on demand', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          as_of: '2026-08-12T18:05:00Z',
          scanned: 1,
          cached: true,
          movers: [{ symbol: 'AAPL', last_price: 200, predicted_price: 202, forecast_change: 0.01, direction: 'up' }],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          as_of: '2026-08-12T19:05:00Z',
          scanned: 1,
          cached: false,
          movers: [{ symbol: 'TSLA', last_price: 250, predicted_price: 270, forecast_change: 0.08, direction: 'up' }],
        }),
      } as Response)
    vi.stubGlobal('fetch', fetch)

    render(<MoversPanel onSelectSymbol={vi.fn()} />)
    expect(await screen.findByRole('button', { name: 'AAPL' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Refresh predicted movers' }))
    expect(await screen.findByRole('button', { name: 'TSLA' })).toBeInTheDocument()
    const body = JSON.parse(String(fetch.mock.calls[1][1].body))
    expect(body.refresh).toBe(true)
  })
})
