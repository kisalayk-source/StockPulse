import { BriefcaseBusiness, LoaderCircle } from 'lucide-react'
import type { Account, Position } from './api'
import { formatCurrency, formatDateTime, formatNumber, formatPercent } from './format'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

export interface HoldSuggestion {
  symbol: string
  projectedMove: number
  holdUntil?: string
}

export function PortfolioPanel({
  account,
  positions,
  state,
  error,
  realizedPl,
  realizedPlState,
  holdSuggestions,
  onSelectSymbol,
}: {
  account: Account | null
  positions: Position[]
  state: LoadState
  error?: string
  realizedPl?: number | null
  realizedPlState?: LoadState
  holdSuggestions?: HoldSuggestion[]
  onSelectSymbol: (symbol: string) => void
}) {
  const sorted = [...positions].sort((a, b) => Math.abs(b.marketValue) - Math.abs(a.marketValue))
  const openPl = positions.reduce((sum, position) => sum + position.unrealizedPl, 0)
  const suggestions = holdSuggestions ?? []

  return (
    <section className="card movers-card portfolio-card" aria-labelledby="portfolio-title">
      <div className="card-heading">
        <div>
          <span className="eyebrow">ACCOUNT</span>
          <h2 id="portfolio-title">Open positions</h2>
        </div>
        <div className="movers-actions">
          <span className="movers-meta">
            {sorted.length ? `${sorted.length} holding${sorted.length === 1 ? '' : 's'}` : 'No open holdings'}
          </span>
        </div>
      </div>

      {account ? (
        <div className="portfolio-summary" aria-label="Account summary">
          <div>
            <span>Equity</span>
            <strong>{formatCurrency(account.equity)}</strong>
          </div>
          <div>
            <span>Buying power</span>
            <strong>{formatCurrency(account.buyingPower)}</strong>
          </div>
          <div>
            <span>Cash</span>
            <strong>{formatCurrency(account.cash)}</strong>
          </div>
          <div>
            <span>Open P/L</span>
            <strong className={openPl >= 0 ? 'positive' : 'negative'}>{formatCurrency(openPl)}</strong>
          </div>
          <div>
            <span>Realized P/L</span>
            <strong
              className={
                realizedPlState === 'ready' && realizedPl != null
                  ? realizedPl >= 0
                    ? 'positive'
                    : 'negative'
                  : undefined
              }
            >
              {realizedPlState === 'loading'
                ? '…'
                : realizedPlState === 'error'
                  ? '—'
                  : realizedPl != null
                    ? formatCurrency(realizedPl)
                    : '—'}
            </strong>
          </div>
        </div>
      ) : null}

      {state === 'loading' && !account && positions.length === 0 ? (
        <div className="movers-status">
          <LoaderCircle className="spin" size={16} />
          Loading portfolio…
        </div>
      ) : state === 'error' && positions.length === 0 ? (
        <div className="movers-status error">{error || 'Unable to load portfolio.'}</div>
      ) : sorted.length === 0 ? (
        <div className="movers-status">
          <BriefcaseBusiness size={16} />
          No open positions.
        </div>
      ) : (
        <div className="movers-table-wrap">
          <table className="movers-table">
            <caption className="sr-only">Open positions</caption>
            <thead>
              <tr>
                <th scope="col">Symbol</th>
                <th scope="col">Qty</th>
                <th scope="col">Avg entry</th>
                <th scope="col">Last</th>
                <th scope="col">Market value</th>
                <th scope="col">% of equity</th>
                <th scope="col">Unrealized P/L</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((position) => {
                const plClass = position.unrealizedPl >= 0 ? 'positive' : 'negative'
                const equityPct = account?.equity
                  ? position.marketValue / account.equity
                  : null
                return (
                  <tr key={position.symbol}>
                    <td>
                      <button type="button" onClick={() => onSelectSymbol(position.symbol)}>
                        {position.symbol}
                      </button>
                    </td>
                    <td>{formatNumber(position.quantity)}</td>
                    <td>{formatCurrency(position.averageEntryPrice)}</td>
                    <td>{formatCurrency(position.currentPrice)}</td>
                    <td>{formatCurrency(position.marketValue)}</td>
                    <td>{equityPct != null ? formatPercent(equityPct, false) : '—'}</td>
                    <td className={plClass}>
                      {formatCurrency(position.unrealizedPl)}
                      {position.unrealizedPlPercent != null
                        ? ` (${formatPercent(position.unrealizedPlPercent, false)})`
                        : ''}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="portfolio-suggestions" aria-live="polite">
        {suggestions.length === 0
          ? 'Hold ideas appear when the movers scan ranks predicted gainers.'
          : (() => {
              const names = suggestions.map((item) => item.symbol)
              const label =
                names.length === 1
                  ? names[0]
                  : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
              const holdUntil = suggestions.map((item) => item.holdUntil).find(Boolean)
              const through = holdUntil ? formatDateTime(holdUntil) : 'the forecast horizon'
              return `Consider ${label} — Kronos projects upside through ${through}. Display-only; not advice.`
            })()}
      </p>

      <p className="disclaimer">
        Live broker positions for the selected paper or live mode. Click a symbol to load it in the
        chart. Orders stay in the Activity tab. Open P/L is mark-to-market on holdings; realized P/L
        is FIFO from closed fills.
      </p>
    </section>
  )
}
