import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const candleSetData = vi.fn()
  const forecastSetData = vi.fn()
  const confidenceSetData = vi.fn()
  const remove = vi.fn()
  const fitContent = vi.fn()
  const addSeries = vi.fn()
  return { candleSetData, forecastSetData, confidenceSetData, remove, fitContent, addSeries }
})

vi.mock('lightweight-charts', () => ({
  CandlestickSeries: 'candlestick',
  LineSeries: 'line',
  ColorType: { Solid: 'solid' },
  createChart: () => ({
    addSeries: mocks.addSeries,
    timeScale: () => ({ fitContent: mocks.fitContent }),
    applyOptions: vi.fn(),
    remove: mocks.remove,
  }),
}))

import { MarketChart } from './MarketChart'

describe('MarketChart', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset())
    let lineSeries = 0
    mocks.addSeries.mockImplementation((type: string) => {
      if (type === 'candlestick') return { setData: mocks.candleSetData }
      lineSeries += 1
      return { setData: lineSeries === 1 ? mocks.forecastSetData : mocks.confidenceSetData }
    })
    vi.stubGlobal('ResizeObserver', class {
      observe = vi.fn()
      disconnect = vi.fn()
    })
  })

  it('maps chart data, exposes an accessible summary, and tears down', () => {
    const view = render(<MarketChart
      candles={[{ time: '2026-08-12T20:00:00Z', open: 99, high: 102, low: 98, close: 101 }]}
      forecast={[{ time: '2026-08-13T20:00:00Z', value: 104, lower: 100, upper: 108 }]}
    />)

    expect(mocks.candleSetData).toHaveBeenCalledOnce()
    expect(mocks.forecastSetData).toHaveBeenCalledOnce()
    expect(mocks.confidenceSetData).toHaveBeenCalledTimes(2)
    expect(view.getByRole('img')).toHaveAccessibleName(/latest close 101.*final forecast 104/i)
    expect(view.getByText(/1 historical candles and 1 forecast points/i)).toBeInTheDocument()

    view.unmount()
    expect(mocks.remove).toHaveBeenCalledOnce()
  })
})
