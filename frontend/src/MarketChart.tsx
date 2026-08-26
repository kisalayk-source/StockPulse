import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Candle, ForecastPoint } from './api'

interface MarketChartProps {
  candles: Candle[]
  forecast: ForecastPoint[]
}

const toTime = (value: string | number): Time =>
  (typeof value === 'number'
    ? value
    : Math.floor(new Date(value).getTime() / 1000)) as UTCTimestamp

export function MarketChart({ candles, forecast }: MarketChartProps) {
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
  }, [candles, forecast])

  const latest = candles.at(-1)
  const predicted = forecast.at(-1)
  return (
    <>
      <div
        className="market-chart"
        ref={containerRef}
        role="img"
        aria-label={`Price and Kronos forecast chart. Latest close ${latest?.close ?? 'unavailable'}. Final forecast ${predicted?.value ?? 'unavailable'}.`}
      />
      <p className="sr-only">
        The chart contains {candles.length} historical candles and {forecast.length} forecast points.
      </p>
    </>
  )
}
