import { ExternalLink, LoaderCircle, RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'
import type { NewsItem } from './api'
import { formatDateTime } from './format'

function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>
}

export function MarketNewsPanel({
  news,
  loading,
  error,
  providerErrors,
  onRefresh,
  onSelectTicker,
}: {
  news: NewsItem[]
  loading: boolean
  error?: string
  providerErrors?: Array<{ provider: string; message: string }>
  onRefresh: () => void
  onSelectTicker?: (ticker: string) => void
}) {
  return (
    <section className="card">
      <div className="card-heading">
        <div>
          <span className="eyebrow">MARKET PULSE</span>
          <h2>Impact-ranked news</h2>
        </div>
        <button className="icon-button" aria-label="Refresh market news" onClick={onRefresh} type="button">
          {loading ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
        </button>
      </div>

      {error && <div className="inline-error" role="alert">{error}</div>}

      {providerErrors && providerErrors.length > 0 && (
        <div className="warning-banner" role="status">
          {providerErrors.map((row) => (
            <div key={`${row.provider}-${row.message}`}>
              {row.provider}: {row.message}
            </div>
          ))}
        </div>
      )}

      <div className="news-grid">
        {loading && !news.length ? (
          <EmptyState>Scanning general market news…</EmptyState>
        ) : news.length ? (
          news.map((item) => (
            <a
              className={`news-card ${item.sentiment || 'neutral'}`}
              key={item.id || item.url}
              href={item.url}
              target="_blank"
              rel="noreferrer"
            >
              <span>
                {item.impact ? `${item.impact.toUpperCase()} · ` : ''}
                {item.source} · {formatDateTime(item.publishedAt)}
                {item.impactScore != null ? ` · score ${item.impactScore.toFixed(1)}` : ''}
              </span>
              <h3>{item.headline}</h3>
              {item.summary && <p>{item.summary}</p>}
              {item.symbols && item.symbols.length > 0 && onSelectTicker && (
                <div className="market-news-tickers">
                  {item.symbols.slice(0, 4).map((ticker) => (
                    <button
                      key={ticker}
                      type="button"
                      className="sec-stat-chip"
                      onClick={(event) => {
                        event.preventDefault()
                        onSelectTicker(ticker)
                      }}
                    >
                      {ticker}
                    </button>
                  ))}
                </div>
              )}
              <ExternalLink size={15} />
            </a>
          ))
        ) : (
          <EmptyState>No ranked market news available.</EmptyState>
        )}
      </div>
    </section>
  )
}