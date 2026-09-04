import type { Candle } from './api'

export type ChopperMaType = 'SMA' | 'EMA'
export type ChopperRegime = 'green' | 'lightgreen' | 'yellow' | 'neutral'
export type ChopperSignal = 'entry' | 'exit'

export interface ChopperConfig {
  maType: ChopperMaType
  fastLength: number
  slowLength: number
  trendLength: number
}

export interface ChopperPoint {
  time: string | number
  fast: number
  slow: number
  regime: ChopperRegime
  signal?: ChopperSignal
}

export const DEFAULT_CHOPPER_CONFIG: ChopperConfig = {
  maType: 'SMA',
  fastLength: 10,
  slowLength: 20,
  trendLength: 5,
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

export function calculateChopper(
  candles: Candle[],
  config: ChopperConfig = DEFAULT_CHOPPER_CONFIG,
): ChopperPoint[] {
  const movingAverage = config.maType === 'EMA' ? exponentialMovingAverage : simpleMovingAverage
  const closes = candles.map((candle) => candle.close)
  const fastValues = movingAverage(closes, config.fastLength)
  const slowValues = movingAverage(closes, config.slowLength)
  const points: ChopperPoint[] = []
  let wasActionable = false

  candles.forEach((candle, index) => {
    const fast = fastValues[index]
    const slow = slowValues[index]
    const priorFast = fastValues[index - config.trendLength]
    const priorSlow = slowValues[index - config.trendLength]
    if (fast == null || slow == null || priorFast == null || priorSlow == null) return

    const fastUp = fast > priorFast
    const slowUp = slow > priorSlow
    let regime: ChopperRegime = 'neutral'
    if (fast > slow && fastUp && slowUp) regime = 'green'
    else if (fast > slow && fastUp && !slowUp) regime = 'lightgreen'
    else if (fast > slow && !fastUp && !slowUp) regime = 'yellow'

    const actionable = regime === 'green' || regime === 'lightgreen'
    const signal = actionable && !wasActionable
      ? 'entry'
      : !actionable && wasActionable
        ? 'exit'
        : undefined
    points.push({ time: candle.time, fast, slow, regime, signal })
    wasActionable = actionable
  })

  return points
}