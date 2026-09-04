import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Candle, ForecastPoint } from './api'
import type { ChopperPoint } from './chopper'

interface MarketChartProps {
  candles: Candle[]
  forecast: ForecastPoint[]
  chopper?: ChopperPoint[]
}

const toTime = (value: string | number): Time =>
  (typeof value === 'number'
    ? value
    : Math.floor(new Date(value).getTime() / 1000)) as UTCTimestamp

const CHOPPER_COLORS = {
  green: '#008f45',
  lightgreen: '#42d978',
  yellow: '#e4c84a',
  neutral: '#768196',
} as const

export function MarketChart({ candles, forecast, chopper }: MarketChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height: Math.max(container.clientHeight, 280),
      layout: {
        background: { type: ColorType.Solid, color: '#0c1018' },
        textColor: '#87909f',
        fontFamily: 'Inter, system-ui, sans-serif',
      },
      grid: {
        vertLines: { color: '#1b2230' },
        horzLines: { color: '#1b2230' },
      },
      rightPriceScale: { borderColor: '#273040' },
      timeScale: { borderColor: '#273040', timeVisible: true },
      crosshair: {
        vertLine: { color: '#526079', labelBackgroundColor: '#273040' },
        horzLine: { color: '#526079', labelBackgroundColor: '#273040' },
      },
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#41c99a',
      downColor: '#f2636b',
      borderVisible: false,
      wickUpColor: '#41c99a',
      wickDownColor: '#f2636b',
    })
    candleSeries.setData(candles.map((item) => ({ ...item, time: toTime(item.time) })))

    if (chopper) {
      chart.addSeries(LineSeries, {
        color: CHOPPER_COLORS.neutral,
        lineWidth: 3,
        priceLineVisible: false,
        title: 'Fast MA (10)',
      }).setData(chopper.map((item) => ({
        time: toTime(item.time),
        value: item.fast,
        color: CHOPPER_COLORS[item.regime],
      })))
      chart.addSeries(LineSeries, {
        color: '#d7dde8',
        lineWidth: 2,
        priceLineVisible: false,
        title: 'Slow MA (20)',
      }).setData(chopper.map((item) => ({ time: toTime(item.time), value: item.slow })))
      const markers: SeriesMarker<Time>[] = chopper.flatMap((item) => item.signal ? [{
        time: toTime(item.time),
        position: item.signal === 'entry' ? 'belowBar' : 'aboveBar',
        shape: item.signal === 'entry' ? 'arrowUp' : 'arrowDown',
        color: item.signal === 'entry' ? '#42d978' : '#f2636b',
        text: item.signal === 'entry' ? 'ENTER' : 'EXIT',
      }] : [])
      createSeriesMarkers(candleSeries, markers)
    } else {
      const forecastSeries = chart.addSeries(LineSeries, {
        color: '#b994ff',
        lineWidth: 3,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        title: 'Kronos forecast',
      })
      forecastSeries.setData(forecast.map((item) => ({ time: toTime(item.time), value: item.value })))

      const confidenceOptions = {
        color: '#76639f',
        lineWidth: 1 as const,
        lineStyle: 2 as const,
        priceLineVisible: false,
        lastValueVisible: false,
      }
      const lower = forecast.filter((item) => item.lower != null)
      const upper = forecast.filter((item) => item.upper != null)
      if (lower.length) {
        chart.addSeries(LineSeries, confidenceOptions)
          .setData(lower.map((item) => ({ time: toTime(item.time), value: item.lower! })))
      }
      if (upper.length) {
        chart.addSeries(LineSeries, confidenceOptions)
          .setData(upper.map((item) => ({ time: toTime(item.time), value: item.upper! })))
      }
    }
    chart.timeScale().fitContent()

    const observer = new ResizeObserver(() => {
      chart.applyOptions({
        width: container.clientWidth,
        height: Math.max(container.clientHeight, 280),
      })
    })
    observer.observe(container)
    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [candles, forecast, chopper])

  const latest = candles.at(-1)
  const predicted = forecast.at(-1)
  return (
    <>
      <div
        className="market-chart"
        ref={containerRef}
        role="img"
        aria-label={chopper
          ? `Price and Chopper signals chart. Latest close ${latest?.close ?? 'unavailable'}. Current regime ${chopper.at(-1)?.regime ?? 'unavailable'}.`
          : `Price and Kronos forecast chart. Latest close ${latest?.close ?? 'unavailable'}. Final forecast ${predicted?.value ?? 'unavailable'}.`}
      />
      <p className="sr-only">
        The chart contains {candles.length} historical candles and {chopper ? `${chopper.length} Chopper points` : `${forecast.length} forecast points`}.
      </p>
    </>
  )
}
