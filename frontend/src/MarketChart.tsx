import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type ISeriesApi,
  type MouseEventParams,
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
  forecastChopper?: ChopperPoint[]
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

const SMA_HOVER_PIXEL_THRESHOLD = 8

function chopperMarkers(points: ChopperPoint[]): SeriesMarker<Time>[] {
  return points.flatMap((item) => item.signal ? [{
    time: toTime(item.time),
    position: item.signal === 'entry' ? 'belowBar' as const : 'aboveBar' as const,
    shape: item.signal === 'entry' ? 'arrowUp' as const : 'arrowDown' as const,
    color: item.signal === 'entry' ? '#42d978' : '#f2636b',
    text: item.signal === 'entry' ? 'ENTER' : 'EXIT',
  }] : [])
}

function nearSmaPrice(
  series: ISeriesApi<'Candlestick'> | ISeriesApi<'Line'>,
  cursorPrice: number,
  targetPrice: number,
): boolean {
  const cursorY = series.priceToCoordinate(cursorPrice)
  const targetY = series.priceToCoordinate(targetPrice)
  if (cursorY == null || targetY == null) return false
  return Math.abs(cursorY - targetY) <= SMA_HOVER_PIXEL_THRESHOLD
}

export function MarketChart({ candles, forecast, chopper, forecastChopper }: MarketChartProps) {
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

    let onCrosshairMove: ((param: MouseEventParams<Time>) => void) | undefined

    const historicalChopper = Boolean(chopper?.length) && forecast.length === 0
    if (historicalChopper && chopper) {
      chart.addSeries(LineSeries, {
        color: CHOPPER_COLORS.neutral,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        title: 'SMA 10',
      }).setData(chopper.map((item) => ({
        time: toTime(item.time),
        value: item.fast,
        color: CHOPPER_COLORS[item.regime],
      })))
      chart.addSeries(LineSeries, {
        color: '#d7dde8',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        title: 'SMA 20',
      }).setData(chopper.map((item) => ({ time: toTime(item.time), value: item.slow })))
      createSeriesMarkers(candleSeries, chopperMarkers(chopper), { zOrder: 'top' })
    } else if (forecast.length) {
      let sma10: ISeriesApi<'Line'> | undefined
      let sma20: ISeriesApi<'Line'> | undefined
      const smaByTime = new Map<Time, { fast: number; slow: number }>()

      if (forecastChopper?.length) {
        for (const item of forecastChopper) {
          smaByTime.set(toTime(item.time), { fast: item.fast, slow: item.slow })
        }
        sma10 = chart.addSeries(LineSeries, {
          color: 'rgba(118, 129, 150, 0.55)',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: 'SMA 10',
          visible: false,
        })
        sma10.setData(forecastChopper.map((item) => ({
          time: toTime(item.time),
          value: item.fast,
        })))
        sma20 = chart.addSeries(LineSeries, {
          color: 'rgba(215, 221, 232, 0.4)',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: 'SMA 20',
          visible: false,
        })
        sma20.setData(forecastChopper.map((item) => ({ time: toTime(item.time), value: item.slow })))
      }

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

      const forecastSeries = chart.addSeries(LineSeries, {
        color: '#b994ff',
        lineWidth: 3,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        title: 'Forecast path',
      })
      forecastSeries.setData(forecast.map((item) => ({ time: toTime(item.time), value: item.value })))

      if (forecastChopper?.length) {
        createSeriesMarkers(forecastSeries, chopperMarkers(forecastChopper), { zOrder: 'top' })
      }

      if (sma10 && sma20) {
        let smaVisible = false
        const setSmaVisible = (visible: boolean) => {
          if (visible === smaVisible) return
          smaVisible = visible
          sma10.applyOptions({ visible })
          sma20.applyOptions({ visible })
        }

        onCrosshairMove = (param) => {
          if (param.time == null || param.point == null) {
            setSmaVisible(false)
            return
          }
          const averages = smaByTime.get(param.time)
          if (!averages) {
            setSmaVisible(false)
            return
          }
          const price = candleSeries.coordinateToPrice(param.point.y)
          if (price == null) {
            setSmaVisible(false)
            return
          }
          const nearFast = nearSmaPrice(candleSeries, price, averages.fast)
          const nearSlow = nearSmaPrice(candleSeries, price, averages.slow)
          setSmaVisible(nearFast || nearSlow)
        }
        chart.subscribeCrosshairMove(onCrosshairMove)
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
      if (onCrosshairMove) chart.unsubscribeCrosshairMove(onCrosshairMove)
      chart.remove()
    }
  }, [candles, forecast, chopper, forecastChopper])

  const latest = candles.at(-1)
  const predicted = forecast.at(-1)
  return (
    <>
      <div
        className="market-chart"
        ref={containerRef}
        role="img"
        aria-label={chopper && !forecast.length
          ? `Price and Chopper signals chart. Latest close ${latest?.close ?? 'unavailable'}. Current regime ${chopper.at(-1)?.regime ?? 'unavailable'}.`
          : `Price and forecast chart. Latest close ${latest?.close ?? 'unavailable'}. Final forecast ${predicted?.value ?? 'unavailable'}${forecastChopper?.length ? `. Forecast Chopper regime ${forecastChopper.at(-1)?.regime ?? 'unavailable'}` : ''}.`}
      />
      <p className="sr-only">
        The chart contains {candles.length} historical candles and {chopper && !forecast.length
          ? `${chopper.length} Chopper points`
          : `${forecast.length} forecast points${forecastChopper?.length ? ` and ${forecastChopper.length} forecast Chopper points` : ''}`}.
      </p>
    </>
  )
}
