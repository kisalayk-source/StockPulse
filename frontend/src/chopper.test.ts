import { describe, expect, it } from 'vitest'
import type { Candle } from './api'
import { calculateChopper, calculateChopperOnForecast } from './chopper'

function candles(closes: number[]): Candle[] {
  return closes.map((close, index) => ({
    time: index,
    open: close,
    high: close,
    low: close,
    close,
  }))
}

describe('calculateChopper', () => {
  it('emits one entry and one exit at causal regime transitions', () => {
    const result = calculateChopper(candles([1, 1, 1, 2, 3, 4, 5, 4, 3]), {
      maType: 'SMA',
      fastLength: 2,
      slowLength: 3,
      trendLength: 1,
    })

    expect(result.map(({ regime, signal }) => ({ regime, signal }))).toEqual([
      { regime: 'green', signal: 'entry' },
      { regime: 'green', signal: undefined },
      { regime: 'green', signal: undefined },
      { regime: 'green', signal: undefined },
      { regime: 'neutral', signal: 'exit' },
      { regime: 'neutral', signal: undefined },
    ])
  })

  it('waits for both averages and the trend lookback', () => {
    const result = calculateChopper(candles([1, 2, 3, 4, 5]), {
      maType: 'EMA',
      fastLength: 2,
      slowLength: 4,
      trendLength: 2,
    })

    expect(result).toEqual([])
  })

  it('projects entry and exit onto the forecast path using prior closes', () => {
    const history = candles([1, 1, 1, 1, 1, 1])
    const forecast = [8, 9, 10, 2, 1].map((value, index) => ({
      time: 100 + index,
      value,
    }))
    const result = calculateChopperOnForecast(history, forecast, {
      maType: 'SMA',
      fastLength: 2,
      slowLength: 3,
      trendLength: 1,
    })

    expect(result.map((point) => point.time)).toEqual([100, 101, 102, 103, 104])
    expect(result.some((point) => point.signal === 'entry')).toBe(true)
    expect(result.some((point) => point.signal === 'exit')).toBe(true)
    expect(result.every((point) => Number(point.time) >= 100)).toBe(true)
  })

  it('starts projected signals flat so an inherited historical long does not exit first', () => {
    // History ends already actionable; forecast leaves then re-enters.
    const history = candles([1, 1, 1, 2, 3, 4, 5, 6, 7])
    const forecast = [8, 9, 1, 1, 10, 11].map((value, index) => ({
      time: 100 + index,
      value,
    }))
    const result = calculateChopperOnForecast(history, forecast, {
      maType: 'SMA',
      fastLength: 2,
      slowLength: 3,
      trendLength: 1,
    })

    const signals = result
      .filter((point) => point.signal)
      .map((point) => point.signal)
    expect(signals[0]).toBe('entry')
    expect(signals).not.toEqual(['exit', 'entry'])
  })
})