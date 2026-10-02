import type { Candle } from './api'

export type OverlayId = 'sma' | 'ema' | 'bollinger' | 'rsi' | 'macd' | 'patterns'

export interface LinePoint {
  time: string | number
  value: number
}

export type PatternKind = 'bullish_engulfing' | 'bearish_engulfing'

export interface PatternMarker {
  time: string | number
  kind: PatternKind
}

export interface IndicatorOverlay {
  sma20: LinePoint[]
  sma50: LinePoint[]
  ema12: LinePoint[]
  ema26: LinePoint[]
  bollingerUpper: LinePoint[]
  bollingerMiddle: LinePoint[]
  bollingerLower: LinePoint[]
  rsi: LinePoint[]
  macd: LinePoint[]
  macdSignal: LinePoint[]
  macdHistogram: LinePoint[]
  patterns: PatternMarker[]
}

export const OVERLAY_LABELS: Record<OverlayId, string> = {
  sma: 'SMA 20 / 50',
  ema: 'EMA 12 / 26',
  bollinger: 'Bollinger',
  rsi: 'RSI 14',
  macd: 'MACD',
  patterns: 'Engulfing',
}

function simpleMovingAverage(values: number[], length: number): Array<number | undefined> {
  let sum = 0
  return values.map((value, index) => {
    sum += value
    if (index >= length) sum -= values[index - length]
    return index >= length - 1 ? sum / length : undefined
  })
}

function exponentialMovingAverage(values: number[], length: number): Array<number | undefined> {
  const result: Array<number | undefined> = Array(values.length).fill(undefined)
  if (values.length < length) return result
  let average = values.slice(0, length).reduce((sum, value) => sum + value, 0) / length
  result[length - 1] = average
  const multiplier = 2 / (length + 1)
  for (let index = length; index < values.length; index += 1) {
    average = (values[index] - average) * multiplier + average
    result[index] = average
  }
  return result
}

function rsiValues(closes: number[], period = 14): Array<number | undefined> {
  const result: Array<number | undefined> = Array(closes.length).fill(undefined)
  if (closes.length <= period) return result

  let gain = 0
  let loss = 0
  for (let index = 1; index <= period; index += 1) {
    const change = closes[index] - closes[index - 1]
    if (change >= 0) gain += change
    else loss -= change
  }
  let avgGain = gain / period
  let avgLoss = loss / period
  result[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)

  for (let index = period + 1; index < closes.length; index += 1) {
    const change = closes[index] - closes[index - 1]
    const up = change > 0 ? change : 0
    const down = change < 0 ? -change : 0
    avgGain = (avgGain * (period - 1) + up) / period
    avgLoss = (avgLoss * (period - 1) + down) / period
    result[index] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  }
  return result
}

/** EMA over defined samples only; maps results back to original indices. */
function sparseEma(
  values: Array<number | undefined>,
  length: number,
): Array<number | undefined> {
  const result: Array<number | undefined> = Array(values.length).fill(undefined)
  const defined = values
    .map((value, index) => ({ value, index }))
    .filter((row): row is { value: number; index: number } => row.value != null && Number.isFinite(row.value))
  if (defined.length < length) return result
  let average = defined.slice(0, length).reduce((sum, row) => sum + row.value, 0) / length
  result[defined[length - 1].index] = average
  const multiplier = 2 / (length + 1)
  for (let cursor = length; cursor < defined.length; cursor += 1) {
    average = (defined[cursor].value - average) * multiplier + average
    result[defined[cursor].index] = average
  }
  return result
}

function pushPoint(
  target: LinePoint[],
  time: string | number,
  value: number | undefined,
): void {
  if (value == null || !Number.isFinite(value)) return
  target.push({ time, value })
}

/** Deterministic chart overlays from historical candles (research only). */
export function calculateOverlays(candles: Candle[]): IndicatorOverlay {
  const closes = candles.map((candle) => candle.close)
  const sma20 = simpleMovingAverage(closes, 20)
  const sma50 = simpleMovingAverage(closes, 50)
  const ema12 = exponentialMovingAverage(closes, 12)
  const ema26 = exponentialMovingAverage(closes, 26)
  const rsi = rsiValues(closes, 14)
  const macdLine = closes.map((_, index) => {
    const fast = ema12[index]
    const slow = ema26[index]
    if (fast == null || slow == null) return undefined
    return fast - slow
  })
  const macdSignal = sparseEma(macdLine, 9)

  const overlay: IndicatorOverlay = {
    sma20: [],
    sma50: [],
    ema12: [],
    ema26: [],
    bollingerUpper: [],
    bollingerMiddle: [],
    bollingerLower: [],
    rsi: [],
    macd: [],
    macdSignal: [],
    macdHistogram: [],
    patterns: [],
  }

  candles.forEach((candle, index) => {
    const mid = sma20[index]
    pushPoint(overlay.sma20, candle.time, mid)
    pushPoint(overlay.sma50, candle.time, sma50[index])
    pushPoint(overlay.ema12, candle.time, ema12[index])
    pushPoint(overlay.ema26, candle.time, ema26[index])
    pushPoint(overlay.rsi, candle.time, rsi[index])

    const macd = macdLine[index]
    const signal = macdSignal[index]
    pushPoint(overlay.macd, candle.time, macd)
    pushPoint(overlay.macdSignal, candle.time, signal)
    if (macd != null && signal != null) {
      pushPoint(overlay.macdHistogram, candle.time, macd - signal)
    }

    if (mid != null && index >= 19) {
      let sumSquares = 0
      for (let offset = 0; offset < 20; offset += 1) {
        const delta = closes[index - offset] - mid
        sumSquares += delta * delta
      }
      const stdev = Math.sqrt(sumSquares / 20)
      pushPoint(overlay.bollingerMiddle, candle.time, mid)
      pushPoint(overlay.bollingerUpper, candle.time, mid + 2 * stdev)
      pushPoint(overlay.bollingerLower, candle.time, mid - 2 * stdev)
    }

    if (index === 0) return
    const prev = candles[index - 1]
    const bullish = candle.close > candle.open
    const bearish = candle.close < candle.open
    const prevBullish = prev.close > prev.open
    const prevBearish = prev.close < prev.open
    if (prevBearish && bullish && candle.open <= prev.close && candle.close >= prev.open) {
      overlay.patterns.push({ time: candle.time, kind: 'bullish_engulfing' })
    } else if (prevBullish && bearish && candle.open >= prev.close && candle.close <= prev.open) {
      overlay.patterns.push({ time: candle.time, kind: 'bearish_engulfing' })
    }
  })

  return overlay
}
