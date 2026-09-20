import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MarketTicker } from './MarketTicker'

const response = (payload: unknown) => ({
  ok: true,
  status: 200,
  json: async () => payload,
}) as Response

describe('MarketTicker', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders sticky tape and selects a symbol', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      items: [{
        symbol: 'SPY',
        price: 500,
        change: 2,
        change_percent: 0.004,
        timestamp: '2026-08-12T18:00:00Z',
      }],
    })))
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1))
    vi.stubGlobal('cancelAnimationFrame', vi.fn())

    const onSelect = vi.fn()
    render(<MarketTicker onSelectSymbol={onSelect} />)

    const buttons = await screen.findAllByRole('button', { name: /SPY/ })
    expect(buttons.length).toBeGreaterThanOrEqual(1)
    fireEvent.click(buttons[0])
    expect(onSelect).toHaveBeenCalledWith('SPY')
  })
})
