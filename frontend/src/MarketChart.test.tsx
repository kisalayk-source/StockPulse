import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const candleSetData = vi.fn()
  const forecastSetData = vi.fn()
  const confidenceSetData = vi.fn()
  const remove = vi.fn()
  const fitContent = vi.fn()
  const addSeries = vi.fn()
  const createSeriesMarkers = vi.fn()
  return { candleSetData, forecastSetData, confidenceSetData, remove, fitContent, addSeries, createSeriesMarkers }
})

vi.mock('lightweight-charts', () => ({
  CandlestickSeries: 'candlestick',
  LineSeries: 'line',
  ColorType: { Solid: 'solid' },
  createSeriesMarkers: mocks.createSeriesMarkers,
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

  it('renders Chopper averages and entry/exit markers instead of a forecast', () => {
    const chopper = [
      { time: 1, fast: 101, slow: 100, regime: 'green' as const, signal: 'entry' as const },
      { time: 2, fast: 99, slow: 100, regime: 'neutral' as const, signal: 'exit' as const },
    ]
    const view = render(<MarketChart
      candles={[
        { time: 1, open: 99, high: 102, low: 98, close: 101 },
        { time: 2, open: 101, high: 102, low: 98, close: 99 },
      ]}
      forecast={[]}
      chopper={chopper}
    />)

    expect(mocks.addSeries).toHaveBeenCalledTimes(3)
    expect(mocks.createSeriesMarkers).toHaveBeenCalledWith(expect.anything(), [
      expect.objectContaining({ text: 'ENTER', shape: 'arrowUp', position: 'belowBar' }),
      expect.objectContaining({ text: 'EXIT', shape: 'arrowDown', position: 'aboveBar' }),
    ])
    expect(view.getByRole('img')).toHaveAccessibleName(/chopper signals.*current regime neutral/i)
    expect(view.getByText(/2 historical candles and 2 chopper points/i)).toBeInTheDocument()
  })
})
