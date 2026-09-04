import { describe, expect, it } from 'vitest'
import type { Candle } from './api'
import { calculateChopper } from './chopper'

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
})