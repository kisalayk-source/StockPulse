import { describe, expect, it } from 'vitest'
import type { Candle } from './api'
import { calculateStrategy } from './strategies'

function risingCandles(n: number): Candle[] {
  return Array.from({ length: n }, (_, index) => {
    const close = 100 + index
    return {
      time: index + 1,
      open: close - 0.4,
      high: close + 0.6,
      low: close - 0.7,
      close,
    }
  })
}

describe('calculateStrategy', () => {
  it('emits chopper points with regimes', () => {
    const points = calculateStrategy('chopper', risingCandles(40))
    expect(points.length).toBeGreaterThan(0)
    expect(points.at(-1)?.regime).toBe('green')
  })

  it('marks MA-cross entry when EMA12 rises through EMA26', () => {
    const base = risingCandles(40)
    const dip = Array.from({ length: 20 }, (_, index) => {
      const close = 140 - index * 2
      return {
        time: 41 + index,
        open: close + 0.3,
        high: close + 0.8,
        low: close - 0.8,
        close,
      }
    })
    const recovery = Array.from({ length: 30 }, (_, index) => {
      const close = 100 + index * 1.5
      return {
        time: 61 + index,
        open: close - 0.3,
        high: close + 0.8,
        low: close - 0.8,
        close,
      }
    })
    const points = calculateStrategy('ma_cross', [...base, ...dip, ...recovery])
    expect(points.some((point) => point.signal === 'entry')).toBe(true)
    expect(points.some((point) => point.signal === 'exit')).toBe(true)
  })

  it('marks BB-revert entry below the lower band', () => {
    const calm = risingCandles(30)
    const crash: Candle[] = Array.from({ length: 5 }, (_, index) => {
      const close = 120 - index * 8
      return {
        time: 31 + index,
        open: close + 2,
        high: close + 3,
        low: close - 3,
        close,
      }
    })
    const points = calculateStrategy('bb_revert', [...calm, ...crash])
    expect(points.some((point) => point.signal === 'entry')).toBe(true)
  })
})
