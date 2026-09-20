import { useEffect, useRef, useState } from 'react'
import { api, type TickerItem } from './api'
import { formatCurrency, formatPercent } from './format'

export function MarketTicker({
  onSelectSymbol,
}: {
  onSelectSymbol?: (symbol: string) => void
}) {
  const [items, setItems] = useState<TickerItem[]>([])
  const viewportRef = useRef<HTMLDivElement>(null)
  const pausedRef = useRef(false)
  const resumeTimerRef = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const payload = await api.marketTicker()
        if (!cancelled) setItems(payload.items)
      } catch {
        if (!cancelled) setItems([])
      }
    }

    void load()
    const timer = window.setInterval(() => void load(), 60_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  // Auto-scroll via scrollLeft — works on iOS Safari where CSS/transform marquees freeze.
  // Do not gate on prefers-reduced-motion: iOS often enables it and users still expect a tape.
  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport || items.length === 0) return

    let frame = 0
    let last = performance.now()
    let running = true
    const speedPxPerSec = 110

    const clearResume = () => {
      if (resumeTimerRef.current != null) {
        window.clearTimeout(resumeTimerRef.current)
        resumeTimerRef.current = null
      }
    }

    const pause = () => {
      pausedRef.current = true
      clearResume()
    }

    const resumeSoon = () => {
      clearResume()
      resumeTimerRef.current = window.setTimeout(() => {
        pausedRef.current = false
        resumeTimerRef.current = null
      }, 900)
    }

    const onMouseLeave = () => {
      pausedRef.current = false
    }

    const step = (now: number) => {
      if (!running) return
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      if (!pausedRef.current) {
        const loopAt = Math.max(1, Math.floor(viewport.scrollWidth / 2))
        if (loopAt > viewport.clientWidth) {
          const next = viewport.scrollLeft + speedPxPerSec * dt
          // Direct assignment — iOS accepts this on overflow containers.
          viewport.scrollLeft = next >= loopAt ? next - loopAt : next
        }
      }
      frame = window.requestAnimationFrame(step)
    }

    // Wait one frame so iOS lays out max-content width before scrolling.
    frame = window.requestAnimationFrame(() => {
      last = performance.now()
      frame = window.requestAnimationFrame(step)
    })

    viewport.addEventListener('touchstart', pause, { passive: true })
    viewport.addEventListener('touchend', resumeSoon, { passive: true })
    viewport.addEventListener('touchcancel', resumeSoon, { passive: true })
    viewport.addEventListener('pointerdown', pause)
    viewport.addEventListener('pointerup', resumeSoon)
    viewport.addEventListener('pointercancel', resumeSoon)
    viewport.addEventListener('mouseenter', pause)
    viewport.addEventListener('mouseleave', onMouseLeave)

    return () => {
      running = false
      window.cancelAnimationFrame(frame)
      clearResume()
      viewport.removeEventListener('touchstart', pause)
      viewport.removeEventListener('touchend', resumeSoon)
      viewport.removeEventListener('touchcancel', resumeSoon)
      viewport.removeEventListener('pointerdown', pause)
      viewport.removeEventListener('pointerup', resumeSoon)
      viewport.removeEventListener('pointercancel', resumeSoon)
      viewport.removeEventListener('mouseenter', pause)
      viewport.removeEventListener('mouseleave', onMouseLeave)
    }
  }, [items])

  if (!items.length) return null

  const tape = [...items, ...items]

  return (
    <div className="market-ticker" role="region" aria-label="Market ticker">
      <div className="market-ticker-viewport" ref={viewportRef}>
        <div className="market-ticker-track">
          {tape.map((item, index) => {
            const tone = (item.changePercent ?? 0) > 0
              ? 'positive'
              : (item.changePercent ?? 0) < 0
                ? 'negative'
                : 'neutral'
            return (
              <button
                key={`${item.symbol}-${index}`}
                type="button"
                className={`market-ticker-item ${tone}`}
                onClick={() => onSelectSymbol?.(item.symbol)}
              >
                <strong>{item.symbol}</strong>
                <span>{formatCurrency(item.price)}</span>
                <span className={tone}>
                  {item.changePercent == null ? '—' : formatPercent(item.changePercent, false)}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
