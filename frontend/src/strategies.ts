import type { Candle, ForecastPoint } from './api'
import { calculateChopper, calculateChopperOnForecast, type ChopperPoint } from './chopper'

export type StrategyEngineId = 'chopper' | 'ma_cross' | 'bb_revert'

export type StrategyPoint = ChopperPoint

export const STRATEGY_ENGINE_IDS: StrategyEngineId[] = ['chopper', 'ma_cross', 'bb_revert']

export const STRATEGY_LABELS: Record<StrategyEngineId, string> = {
  chopper: 'Chopper',
  ma_cross: 'MA Cross',
  bb_revert: 'BB Revert',
}

export const STRATEGY_META: Record<StrategyEngineId, {
  fastLabel: string
  slowLabel: string
  note: string
  projectedNote: string
  meta: string
}> = {
  chopper: {
    fastLabel: 'SMA 10',
    slowLabel: 'SMA 20',
    note: 'Enter when the 10-bar average is above the 20-bar average and rising versus five bars ago. Exit when that condition ends. Signals use closing-bar data only and never place orders.',
    projectedNote: 'Projected enter and exit markers use the forecast close path plus recent candles so the averages can warm up. Markers start flat at the forecast start. They never place orders.',
    meta: 'trend lookback 5 bars · closing-bar signals',
  },
  ma_cross: {
    fastLabel: 'EMA 12',
    slowLabel: 'EMA 26',
    note: 'Enter on a golden cross (EMA 12 crosses above EMA 26). Exit on a death cross. Closing-bar signals only; never places orders.',
    projectedNote: 'Projected MA-cross markers warm on history then mark crosses on the forecast path only. They never place orders.',
    meta: 'EMA 12 / 26 cross · closing-bar signals',
  },
  bb_revert: {
    fastLabel: 'BB mid',
    slowLabel: 'BB lower',
    note: 'Mean-revert long: enter when close crosses below the lower Bollinger band; exit when close crosses back above the middle band. Research only; never places orders.',
    projectedNote: 'Projected Bollinger markers warm on history then fire on the forecast path only. They never place orders.',
    meta: 'Bollinger 20 / 2σ mean revert · closing-bar signals',
  },
}

export function isStrategyEngine(value: string): value is StrategyEngineId {
  return STRATEGY_ENGINE_IDS.includes(value as StrategyEngineId)
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

function simpleMovingAverage(values: number[], length: number): Array<number | undefined> {
  let sum = 0
  return values.map((value, index) => {
    sum += value
    if (index >= length) sum -= values[index - length]
    return index >= length - 1 ? sum / length : undefined
  })
}

function calculateMaCross(candles: Candle[]): StrategyPoint[] {
  const closes = candles.map((candle) => candle.close)
  const fastValues = exponentialMovingAverage(closes, 12)
  const slowValues = exponentialMovingAverage(closes, 26)
  const points: StrategyPoint[] = []

  candles.forEach((candle, index) => {
    const fast = fastValues[index]
    const slow = slowValues[index]
    const priorFast = fastValues[index - 1]
    const priorSlow = slowValues[index - 1]
    if (fast == null || slow == null) return

    const long = fast > slow
    let signal: StrategyPoint['signal']
    if (priorFast != null && priorSlow != null) {
      const wasAbove = priorFast > priorSlow
      if (long && !wasAbove) signal = 'entry'
      else if (!long && wasAbove) signal = 'exit'
    }

    points.push({
      time: candle.time,
      fast,
      slow,
      regime: long ? 'green' : 'neutral',
      signal,
    })
  })

  return points
}

function calculateBbRevert(candles: Candle[]): StrategyPoint[] {
  const closes = candles.map((candle) => candle.close)
  const midValues = simpleMovingAverage(closes, 20)
  const points: StrategyPoint[] = []
  let inPosition = false

  candles.forEach((candle, index) => {
    const mid = midValues[index]
    if (mid == null || index < 19) return
    let sumSquares = 0
    for (let offset = 0; offset < 20; offset += 1) {
      const delta = closes[index - offset] - mid
      sumSquares += delta * delta
    }
    const stdev = Math.sqrt(sumSquares / 20)
    const lower = mid - 2 * stdev
    const priorClose = closes[index - 1]
    const close = closes[index]

    let signal: StrategyPoint['signal']
    if (!inPosition && priorClose != null && priorClose >= lower && close < lower) {
      signal = 'entry'
      inPosition = true
    } else if (inPosition && priorClose != null && priorClose <= mid && close > mid) {
      signal = 'exit'
      inPosition = false
    }

    points.push({
      time: candle.time,
      fast: mid,
      slow: lower,
      regime: inPosition || signal === 'entry' ? 'lightgreen' : 'neutral',
      signal,
    })
  })

  return points
}

function forecastAsCandles(points: ForecastPoint[]): Candle[] {
  return points.map((point) => ({
    time: point.time,
    open: point.value,
    high: point.value,
    low: point.value,
    close: point.value,
  }))
}

function projectStrategy(
  candles: Candle[],
  forecast: ForecastPoint[],
  calculate: (rows: Candle[]) => StrategyPoint[],
): StrategyPoint[] {
  if (!candles.length || !forecast.length) return []
  const forecastTimes = new Set(forecast.map((point) => String(point.time)))
  const projected = calculate([...candles, ...forecastAsCandles(forecast)])
    .filter((point) => forecastTimes.has(String(point.time)))
  let wasActionable = false
  return projected.map((point) => {
    const actionable = point.regime === 'green' || point.regime === 'lightgreen'
    const signal = actionable && !wasActionable
      ? 'entry'
      : !actionable && wasActionable
        ? 'exit'
        : undefined
    wasActionable = actionable
    return { ...point, signal }
  })
}

export function calculateStrategy(
  engine: StrategyEngineId,
  candles: Candle[],
): StrategyPoint[] {
  if (engine === 'chopper') return calculateChopper(candles)
  if (engine === 'ma_cross') return calculateMaCross(candles)
  return calculateBbRevert(candles)
}

export function calculateStrategyOnForecast(
  engine: StrategyEngineId,
  candles: Candle[],
  forecast: ForecastPoint[],
): StrategyPoint[] {
  if (engine === 'chopper') return calculateChopperOnForecast(candles, forecast)
  if (engine === 'ma_cross') return projectStrategy(candles, forecast, calculateMaCross)
  return projectStrategy(candles, forecast, calculateBbRevert)
}
