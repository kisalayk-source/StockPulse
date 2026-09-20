import { useEffect, useState } from 'react'
import { api, type TickerItem } from './api'
import { formatCurrency, formatPercent } from './format'

export function MarketTicker({
  onSelectSymbol,
}: {
  onSelectSymbol?: (symbol: string) => void
}) {
  const [items, setItems] = useState<TickerItem[]>([])

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

  if (!items.length) return null

  const tape = [...items, ...items]

  return (
    <div className="market-ticker" role="region" aria-label="Market ticker">
      <div className="market-ticker-viewport">
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
