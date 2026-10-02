import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  type ISeriesApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Candle, ForecastPoint } from './api'
import type { ChopperPoint } from './chopper'
import type { IndicatorOverlay, OverlayId } from './indicators'

interface MarketChartProps {
  candles: Candle[]
  forecast: ForecastPoint[]
  chopper?: ChopperPoint[]
  forecastChopper?: ChopperPoint[]
  overlays?: IndicatorOverlay
  activeOverlays?: OverlayId[]
  strategyFastTitle?: string
  strategySlowTitle?: string
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

function strategyMarkers(points: ChopperPoint[]): SeriesMarker<Time>[] {
  return points.flatMap((item) => item.signal ? [{
    time: toTime(item.time),
    position: item.signal === 'entry' ? 'belowBar' as const : 'aboveBar' as const,
    shape: item.signal === 'entry' ? 'arrowUp' as const : 'arrowDown' as const,
    color: item.signal === 'entry' ? '#42d978' : '#f2636b',
    text: item.signal === 'entry' ? 'ENTER' : 'EXIT',
  }] : [])
}

function patternMarkers(overlays: IndicatorOverlay): SeriesMarker<Time>[] {
  return overlays.patterns.map((item) => ({
    time: toTime(item.time),
    position: item.kind === 'bullish_engulfing' ? 'belowBar' as const : 'aboveBar' as const,
    shape: item.kind === 'bullish_engulfing' ? 'arrowUp' as const : 'arrowDown' as const,
    color: item.kind === 'bullish_engulfing' ? '#6ea8fe' : '#e89b5c',
    text: item.kind === 'bullish_engulfing' ? 'BULL ENG' : 'BEAR ENG',
  }))
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

function lineData(points: { time: string | number; value: number }[]) {
  return points.map((item) => ({ time: toTime(item.time), value: item.value }))
}

export function MarketChart({
  candles,
  forecast,
  chopper,
  forecastChopper,
  overlays,
  activeOverlays = [],
  strategyFastTitle = 'SMA 10',
  strategySlowTitle = 'SMA 20',
}: MarketChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const showSma = activeOverlays.includes('sma')
  const showEma = activeOverlays.includes('ema')
  const showBollinger = activeOverlays.includes('bollinger')
  const showRsi = activeOverlays.includes('rsi')
  const showMacd = activeOverlays.includes('macd')
  const showPatterns = activeOverlays.includes('patterns')
  const paneCount = 1 + (showRsi ? 1 : 0) + (showMacd ? 1 : 0)
  const chartHeight = Math.max(280, 280 + (paneCount - 1) * 90)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height: Math.max(container.clientHeight, chartHeight),
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
    let nextPane = 1

    if (overlays && showSma) {
      if (overlays.sma20.length) {
        chart.addSeries(LineSeries, {
          color: '#6ea8fe',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: 'SMA 20',
        }).setData(lineData(overlays.sma20))
      }
      if (overlays.sma50.length) {
        chart.addSeries(LineSeries, {
          color: '#f0b429',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: 'SMA 50',
        }).setData(lineData(overlays.sma50))
      }
    }

    if (overlays && showEma) {
      if (overlays.ema12.length) {
        chart.addSeries(LineSeries, {
          color: '#5ad1c8',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: 'EMA 12',
        }).setData(lineData(overlays.ema12))
      }
      if (overlays.ema26.length) {
        chart.addSeries(LineSeries, {
          color: '#c792ea',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: 'EMA 26',
        }).setData(lineData(overlays.ema26))
      }
    }

    if (overlays && showBollinger) {
      const bandOptions = {
        lineWidth: 1 as const,
        lineStyle: 2 as const,
        priceLineVisible: false,
        lastValueVisible: false,
      }
      if (overlays.bollingerUpper.length) {
        chart.addSeries(LineSeries, { ...bandOptions, color: 'rgba(118, 129, 150, 0.85)', title: 'BB upper' })
          .setData(lineData(overlays.bollingerUpper))
      }
      if (overlays.bollingerMiddle.length) {
        chart.addSeries(LineSeries, { ...bandOptions, color: 'rgba(215, 221, 232, 0.55)', title: 'BB mid' })
          .setData(lineData(overlays.bollingerMiddle))
      }
      if (overlays.bollingerLower.length) {
        chart.addSeries(LineSeries, { ...bandOptions, color: 'rgba(118, 129, 150, 0.85)', title: 'BB lower' })
          .setData(lineData(overlays.bollingerLower))
      }
    }

    if (overlays && showRsi && overlays.rsi.length) {
      const rsiPane = nextPane
      nextPane += 1
      chart.addSeries(LineSeries, {
        color: '#e89b5c',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        title: 'RSI 14',
      }, rsiPane).setData(lineData(overlays.rsi))
    }

    if (overlays && showMacd && overlays.macd.length) {
      const macdPane = nextPane
      nextPane += 1
      if (overlays.macdHistogram.length) {
        chart.addSeries(HistogramSeries, {
          color: 'rgba(118, 129, 150, 0.55)',
          priceLineVisible: false,
          lastValueVisible: false,
          title: 'MACD hist',
        }, macdPane).setData(lineData(overlays.macdHistogram).map((item) => ({
          ...item,
          color: item.value >= 0 ? 'rgba(65, 201, 154, 0.55)' : 'rgba(242, 99, 107, 0.55)',
        })))
      }
      chart.addSeries(LineSeries, {
        color: '#6ea8fe',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        title: 'MACD',
      }, macdPane).setData(lineData(overlays.macd))
      if (overlays.macdSignal.length) {
        chart.addSeries(LineSeries, {
          color: '#f0b429',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: 'MACD signal',
        }, macdPane).setData(lineData(overlays.macdSignal))
      }
    }

    const markers: SeriesMarker<Time>[] = []
    if (overlays && showPatterns) {
      markers.push(...patternMarkers(overlays))
    }

    const historicalStrategy = Boolean(chopper?.length) && forecast.length === 0
    if (historicalStrategy && chopper) {
      chart.addSeries(LineSeries, {
        color: CHOPPER_COLORS.neutral,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        title: strategyFastTitle,
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
        title: strategySlowTitle,
      }).setData(chopper.map((item) => ({ time: toTime(item.time), value: item.slow })))
      markers.push(...strategyMarkers(chopper))
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
          title: strategyFastTitle,
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
          title: strategySlowTitle,
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
        createSeriesMarkers(forecastSeries, strategyMarkers(forecastChopper), { zOrder: 'top' })
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

    if (markers.length) {
      markers.sort((left, right) => Number(left.time) - Number(right.time))
      createSeriesMarkers(candleSeries, markers, { zOrder: 'top' })
    }

    chart.timeScale().fitContent()

    const observer = new ResizeObserver(() => {
      chart.applyOptions({
        width: container.clientWidth,
        height: Math.max(container.clientHeight, chartHeight),
      })
    })
    observer.observe(container)
    return () => {
      observer.disconnect()
      if (onCrosshairMove) chart.unsubscribeCrosshairMove(onCrosshairMove)
      chart.remove()
    }
  }, [
    candles,
    forecast,
    chopper,
    forecastChopper,
    overlays,
    showSma,
    showEma,
    showBollinger,
    showRsi,
    showMacd,
    showPatterns,
    chartHeight,
    strategyFastTitle,
    strategySlowTitle,
  ])

  const latest = candles.at(-1)
  const predicted = forecast.at(-1)
  const overlayLabel = activeOverlays.length
    ? ` Overlays ${activeOverlays.join(', ')}.`
    : ''
  return (
    <>
      <div
        className="market-chart"
        ref={containerRef}
        role="img"
        aria-label={chopper && !forecast.length
          ? `Price and strategy signals chart. Latest close ${latest?.close ?? 'unavailable'}. Current regime ${chopper.at(-1)?.regime ?? 'unavailable'}.${overlayLabel}`
          : `Price and forecast chart. Latest close ${latest?.close ?? 'unavailable'}. Final forecast ${predicted?.value ?? 'unavailable'}${forecastChopper?.length ? `. Forecast strategy regime ${forecastChopper.at(-1)?.regime ?? 'unavailable'}` : ''}.${overlayLabel}`}
      />
      <p className="sr-only">
        The chart contains {candles.length} historical candles and {chopper && !forecast.length
          ? `${chopper.length} strategy points`
          : `${forecast.length} forecast points${forecastChopper?.length ? ` and ${forecastChopper.length} forecast strategy points` : ''}`}
        {activeOverlays.length ? ` with overlays ${activeOverlays.join(', ')}` : ''}.
      </p>
    </>
  )
}
