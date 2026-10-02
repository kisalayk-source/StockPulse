import { describe, expect, it } from 'vitest'
import { calculateOverlays } from './indicators'
import type { Candle } from './api'

function candles(n: number, seed = 1): Candle[] {
  const rows: Candle[] = []
  let close = 100
  for (let index = 0; index < n; index += 1) {
    close += ((index * seed) % 7) - 3
    const open = close - ((index % 2 === 0) ? 1 : -1)
    rows.push({
      time: index + 1,
      open,
      high: Math.max(open, close) + 1,
      low: Math.min(open, close) - 1,
      close,
    })
  }
  return rows
}

describe('calculateOverlays', () => {
  it('is deterministic and warms SMA / EMA / Bollinger / RSI / MACD windows', () => {
    const input = candles(80)
    const first = calculateOverlays(input)
    const second = calculateOverlays(input)
    expect(first).toEqual(second)
    expect(first.sma20.length).toBe(input.length - 19)
    expect(first.sma50.length).toBe(input.length - 49)
    expect(first.ema12.length).toBe(input.length - 11)
    expect(first.ema26.length).toBe(input.length - 25)
    expect(first.bollingerUpper.length).toBe(first.sma20.length)
    expect(first.rsi.length).toBe(input.length - 14)
    expect(first.macd.length).toBe(first.ema26.length)
    expect(first.macdSignal.length).toBeGreaterThan(0)
    expect(first.macdHistogram.length).toBe(first.macdSignal.length)
    expect(first.rsi.every((point) => point.value >= 0 && point.value <= 100)).toBe(true)
  })

  it('flags engulfing patterns when bodies wrap the prior candle', () => {
    const rows: Candle[] = [
      { time: 1, open: 10, high: 11, low: 9, close: 10.5 },
      { time: 2, open: 10.4, high: 10.5, low: 9.5, close: 9.6 }, // bearish
      { time: 3, open: 9.5, high: 11, low: 9.4, close: 10.5 }, // bullish engulfing
      { time: 4, open: 10.2, high: 10.8, low: 10, close: 10.6 }, // bullish
      { time: 5, open: 10.7, high: 10.8, low: 9.8, close: 9.9 }, // bearish engulfing
    ]
    const overlay = calculateOverlays(rows)
    expect(overlay.patterns).toEqual([
      { time: 3, kind: 'bullish_engulfing' },
      { time: 5, kind: 'bearish_engulfing' },
    ])
  })

  it('returns empty series for short history', () => {
    const empty = calculateOverlays(candles(5))
    expect(empty.sma20).toEqual([])
    expect(empty.ema26).toEqual([])
    expect(empty.macd).toEqual([])
    expect(empty.rsi).toEqual([])
  })
})
