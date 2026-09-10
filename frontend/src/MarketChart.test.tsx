import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const candleSetData = vi.fn()
  const forecastSetData = vi.fn()
  const confidenceSetData = vi.fn()
  const smaSetData = vi.fn()
  const applyOptions = vi.fn()
  const remove = vi.fn()
  const fitContent = vi.fn()
  const addSeries = vi.fn()
  const createSeriesMarkers = vi.fn()
  const subscribeCrosshairMove = vi.fn()
  const unsubscribeCrosshairMove = vi.fn()
  return {
    candleSetData,
    forecastSetData,
    confidenceSetData,
    smaSetData,
    applyOptions,
    remove,
    fitContent,
    addSeries,
    createSeriesMarkers,
    subscribeCrosshairMove,
    unsubscribeCrosshairMove,
  }
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
    subscribeCrosshairMove: mocks.subscribeCrosshairMove,
    unsubscribeCrosshairMove: mocks.unsubscribeCrosshairMove,
    remove: mocks.remove,
  }),
}))

import { MarketChart } from './MarketChart'

describe('MarketChart', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset())
    let lineSeries = 0
    mocks.addSeries.mockImplementation((type: string, options?: { title?: string; visible?: boolean }) => {
      if (type === 'candlestick') {
        return {
          setData: mocks.candleSetData,
          applyOptions: mocks.applyOptions,
          coordinateToPrice: vi.fn(),
          priceToCoordinate: vi.fn(),
        }
      }
      lineSeries += 1
      const setData = options?.title === 'Forecast path'
        ? mocks.forecastSetData
        : options?.title?.startsWith('SMA')
          ? mocks.smaSetData
          : mocks.confidenceSetData
      return {
        setData,
        applyOptions: mocks.applyOptions,
        coordinateToPrice: vi.fn(),
        priceToCoordinate: vi.fn(),
      }
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
    expect(mocks.createSeriesMarkers).toHaveBeenCalledWith(
      expect.anything(),
      [
        expect.objectContaining({ text: 'ENTER', shape: 'arrowUp', position: 'belowBar' }),
        expect.objectContaining({ text: 'EXIT', shape: 'arrowDown', position: 'aboveBar' }),
      ],
      { zOrder: 'top' },
    )
    expect(view.getByRole('img')).toHaveAccessibleName(/chopper signals.*current regime neutral/i)
    expect(view.getByText(/2 historical candles and 2 chopper points/i)).toBeInTheDocument()
  })

  it('hides forecast SMA overlays until hover and stacks enter/exit markers on top', () => {
    const forecastChopper = [
      { time: '2026-08-13T20:00:00Z', fast: 103, slow: 102, regime: 'green' as const, signal: 'entry' as const },
      { time: '2026-08-14T20:00:00Z', fast: 101, slow: 102, regime: 'neutral' as const, signal: 'exit' as const },
    ]
    const view = render(<MarketChart
      candles={[{ time: '2026-08-12T20:00:00Z', open: 99, high: 102, low: 98, close: 101 }]}
      forecast={[
        { time: '2026-08-13T20:00:00Z', value: 104, lower: 100, upper: 108 },
        { time: '2026-08-14T20:00:00Z', value: 100, lower: 96, upper: 104 },
      ]}
      forecastChopper={forecastChopper}
    />)

    expect(mocks.addSeries).toHaveBeenCalledWith('line', expect.objectContaining({ title: 'SMA 10', visible: false }))
    expect(mocks.addSeries).toHaveBeenCalledWith('line', expect.objectContaining({ title: 'SMA 20', visible: false }))
    expect(mocks.smaSetData).toHaveBeenCalledTimes(2)
    expect(mocks.subscribeCrosshairMove).toHaveBeenCalledOnce()
    expect(mocks.createSeriesMarkers).toHaveBeenCalledWith(
      expect.anything(),
      [
        expect.objectContaining({ text: 'ENTER', shape: 'arrowUp', position: 'belowBar' }),
        expect.objectContaining({ text: 'EXIT', shape: 'arrowDown', position: 'aboveBar' }),
      ],
      { zOrder: 'top' },
    )

    view.unmount()
    expect(mocks.unsubscribeCrosshairMove).toHaveBeenCalledOnce()
  })
})
