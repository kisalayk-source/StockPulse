import { useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import type {
  AccumulationScanStatus,
  ResearchQueryResponse,
  SecFilingsResponse,
  SecIntelligenceResponse,
  SectorAccumulationResponse,
  TopAccumulationResponse,
} from './api'
import { formatDateTime, formatNumber } from './format'

function scoreBarClass(score: number | undefined): string {
  if (score == null) return 'neutral'
  if (score >= 60) return 'positive'
  if (score <= 39) return 'negative'
  return 'neutral'
}

function accumulationBand(score: number | undefined): string {
  if (score == null) return 'Unknown'
  if (score >= 60) return 'Accumulation'
  if (score <= 39) return 'Distribution'
  return 'Neutral'
}

function accumulationBandClass(score: number | undefined): string {
  if (score == null) return 'neutral'
  if (score >= 60) return 'positive'
  if (score <= 39) return 'negative'
  return 'neutral'
}

function ScoreBar({ label, score }: { label: string; score?: number }) {
  const value = score ?? 0
  return (
    <div className="sec-score-row">
      <div className="sec-score-label">
        <span>{label}</span>
        <strong>{score != null ? formatNumber(Math.round(score)) : '—'}</strong>
      </div>
      <div className="sec-score-bar" aria-hidden="true">
        <span className={scoreBarClass(score)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
    </div>
  )
}

export function ScanProgressBanner({ progress }: { progress: AccumulationScanStatus | null }) {
  if (!progress || ['idle', 'ready', 'disabled'].includes(progress.status)) return null
  const pct = progress.total > 0 ? Math.round((progress.scanned / progress.total) * 100) : 0
  return (
    <div className="sec-scan-banner" role="status">
      <span>
        {progress.status === 'error'
          ? (progress.error || 'Market scan failed')
          : `Scanning market tickers… ${progress.scanned}/${progress.total} (${pct}%)`}
      </span>
      <div className="sec-scan-bar" aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function SecIntelligencePanel({
  data,
  loading,
  error,
}: {
  data: SecIntelligenceResponse | null
  loading: boolean
  error?: string
}) {
  if (loading) {
    return (
      <section className="card sec-card">
        <div className="card-heading"><div><span className="eyebrow">SEC & OWNERSHIP</span><h2>SEC Intelligence</h2></div></div>
        <div className="empty-state">Loading SEC intelligence…</div>
      </section>
    )
  }
  if (error) {
    return (
      <section className="card sec-card muted-card">
        <div className="card-heading"><div><span className="eyebrow">SEC & OWNERSHIP</span><h2>SEC Intelligence</h2></div></div>
        <div className="empty-state">{error}</div>
      </section>
    )
  }
  if (!data) return null
  const acc = data.accumulation
  const stale = Boolean(data.provider_errors?.length)
  return (
    <section className={`card sec-card${stale ? ' muted-card' : ''}`}>
      <div className="card-heading">
        <div>
          <span className="eyebrow">SEC & OWNERSHIP INTELLIGENCE</span>
          <h2>{data.ticker} accumulation</h2>
        </div>
        <div className={`sec-signal ${acc.signal.toLowerCase()}`}>{acc.classification.replaceAll('_', ' ')}</div>
      </div>
      <div className="sec-headline">
        <div>
          <span className="label">Accumulation Score</span>
          <div className="sec-overall-score">{formatNumber(Math.round(acc.score))} <small>/ 100</small></div>
        </div>
        <div className="sec-as-of">As of {formatDateTime(acc.as_of)}</div>
      </div>
      <ScoreBar label="Institutional" score={acc.components.institutional} />
      <ScoreBar label="Insiders" score={acc.components.insider} />
      <ScoreBar label="Major Holders" score={acc.components.major_holder} />
      <ScoreBar label="Price/Volume" score={acc.components.price_volume} />
      <ScoreBar label="Fundamentals" score={acc.components.fundamentals} />
      {acc.history.length > 0 && (
        <div className="sec-history">
          <span className="label">Accumulation trend</span>
          <div className="sec-history-grid">
            {acc.history.slice(-6).map((point) => (
              <div key={point.date} className="sec-history-point">
                <strong>{formatNumber(Math.round(point.score))}</strong>
                <small>{point.date.slice(0, 7)}</small>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="sec-columns">
        <div>
          <h3>Recent institutional changes</h3>
          <ul>
            {data.institutional_changes.slice(0, 5).map((row, idx) => (
              <li key={idx}>{String(row.manager)} — {String(row.classification)} ({String(row.reporting_period || 'n/a')})</li>
            ))}
            {!data.institutional_changes.length && <li>No recent 13F position changes.</li>}
          </ul>
        </div>
        <div>
          <h3>Recent insider transactions</h3>
          <ul>
            {data.insider_transactions.slice(0, 5).map((row, idx) => (
              <li key={idx}>{String(row.insider)} — {String(row.normalized_type)} ({String(row.transaction_date || 'n/a')})</li>
            ))}
            {!data.insider_transactions.length && <li>No recent Form 4 transactions.</li>}
          </ul>
        </div>
      </div>
      <ul className="sec-caveats">
        {data.caveats.map((item) => <li key={item}>{item}</li>)}
      </ul>
      <p className="disclaimer">
        Accumulation scores are research signals based on SEC filings and market data — not investment advice or trade signals.
      </p>
    </section>
  )
}

export function SectorsPanel({
  sectors,
  loading,
  error,
  scanProgress,
  onSelectSector,
  onSelectTicker,
}: {
  sectors: SectorAccumulationResponse[]
  loading: boolean
  error?: string
  scanProgress?: AccumulationScanStatus | null
  onSelectSector?: (sector: string) => void
  onSelectTicker?: (ticker: string) => void
}) {
  return (
    <section className="card sec-card">
      <div className="card-heading"><div><span className="eyebrow">SECTOR ANALYSIS</span><h2>SEC accumulation by sector</h2></div></div>
      <p className="sec-help">
        Accumulation scores (0–100) combine institutional, insider, and major-holder filings. Higher scores suggest more buying interest; lower scores suggest selling pressure.
      </p>
      <ScanProgressBanner progress={scanProgress || null} />
      {loading ? <div className="empty-state">Loading sector metrics…</div> : error ? (
        <div className="empty-state">{error}</div>
      ) : !sectors.length ? (
        <div className="empty-state">No sector data yet. Market scan in progress…</div>
      ) : (
        <div className="sec-sector-grid">
          {sectors.map((row) => (
            <div key={row.sector} className="sec-sector-card">
              <button type="button" className="sec-sector-head" onClick={() => onSelectSector?.(row.sector)}>
                <strong>{row.sector}</strong>
                <span className={`sec-band ${accumulationBandClass(row.avg_score)}`}>
                  Avg accumulation: {formatNumber(Math.round(row.avg_score))} ({accumulationBand(row.avg_score)})
                </span>
              </button>
              <div className="sec-sector-meta">
                <span>{formatNumber(Math.round(row.pct_increasing))}% trending up</span>
                <span>{formatNumber(Math.round(row.pct_decreasing))}% trending down</span>
                <span>{row.ticker_count ?? row.stocks.length} tickers</span>
              </div>
              <ul className="sec-sector-tickers">
                {row.stocks.slice(0, 5).map((stock) => (
                  <li key={stock.ticker}>
                    <button type="button" onClick={() => onSelectTicker?.(stock.ticker)}>
                      {stock.ticker}{' '}
                      <span className={`sec-band ${accumulationBandClass(stock.score)}`}>
                        {accumulationBand(stock.score)} ({formatNumber(Math.round(stock.score))})
                      </span>
                    </button>
                  </li>
                ))}
                {!row.stocks.length && <li className="muted">No scored tickers in this sector yet.</li>}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export function TopAccumulationPanel({
  data,
  loading,
  error,
  scanProgress,
  onSelectTicker,
}: {
  data: TopAccumulationResponse | null
  loading: boolean
  error?: string
  scanProgress?: AccumulationScanStatus | null
  onSelectTicker?: (ticker: string) => void
}) {
  const rows = data?.results || []
  return (
    <section className="card sec-card">
      <div className="card-heading"><div><span className="eyebrow">TOP ACCUMULATION</span><h2>Top accumulation stocks</h2></div></div>
      <ScanProgressBanner progress={scanProgress || null} />
      {loading ? <div className="empty-state">Loading top accumulation…</div> : error ? (
        <div className="empty-state">{error}</div>
      ) : !rows.length ? (
        <div className="empty-state">
          {scanProgress && !['idle', 'ready'].includes(scanProgress.status)
            ? 'Scanning market tickers… scores will appear as the scan progresses.'
            : 'No accumulation scores yet. Try refreshing the market scan.'}
        </div>
      ) : (
        <table className="sec-table">
          <thead>
            <tr><th>Ticker</th><th>Sector</th><th>Accumulation score</th><th>Signal</th><th>Institutional</th><th>Insider</th></tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.ticker} className="clickable" onClick={() => onSelectTicker?.(row.ticker)}>
                <td>{row.ticker}</td>
                <td>{row.sector || '—'}</td>
                <td>
                  {formatNumber(Math.round(row.score))}{' '}
                  <span className={`sec-band ${accumulationBandClass(row.score)}`}>({accumulationBand(row.score)})</span>
                </td>
                <td>{row.classification.replaceAll('_', ' ')}</td>
                <td>{formatNumber(Math.round(row.components.institutional ?? 0))}</td>
                <td>{formatNumber(Math.round(row.components.insider ?? 0))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export function ResearchPanel({
  response,
  loading,
  error,
  scanProgress,
  onSubmit,
}: {
  response: ResearchQueryResponse | null
  loading: boolean
  error?: string
  scanProgress?: AccumulationScanStatus | null
  onSubmit: (query: string) => void
}) {
  const [query, setQuery] = useState('')
  return (
    <section className="card sec-card">
      <div className="card-heading"><div><span className="eyebrow">AI RESEARCH</span><h2>SEC-aware research query</h2></div></div>
      <ScanProgressBanner progress={scanProgress || null} />
      <form className="research-form" onSubmit={(event) => { event.preventDefault(); onSubmit(query) }}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Which energy stocks have strong institutional accumulation?" />
        <button type="submit" disabled={loading || query.trim().length < 3}>{loading ? 'Searching…' : 'Research'}</button>
      </form>
      {error && <div className="empty-state">{error}</div>}
      {response && (
        <>
          {response.candidates.length > 0 ? (
            <table className="sec-table research-candidates">
              <thead>
                <tr><th>Ticker</th><th>Accumulation score</th><th>Signal</th><th>Why</th></tr>
              </thead>
              <tbody>
                {response.candidates.map((row) => (
                  <tr key={row.ticker}>
                    <td>{row.ticker}</td>
                    <td>{formatNumber(Math.round(row.accumulation_score))}</td>
                    <td>{row.signal?.replaceAll('_', ' ') || '—'}</td>
                    <td>{row.why || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">No matching candidates in the current score cache.</div>
          )}
          <div className="research-narrative">{response.narrative}</div>
          <p className="disclaimer">{response.disclaimer}</p>
        </>
      )}
    </section>
  )
}

export function SecRecordsPanel({
  symbol,
  data,
  loading,
  error,
  onSearch,
}: {
  symbol: string
  data: SecFilingsResponse | null
  loading: boolean
  error?: string
  onSearch: (ticker: string) => void
}) {
  const [query, setQuery] = useState(symbol)
  useEffect(() => { setQuery(symbol) }, [symbol])

  return (
    <section className="card sec-card">
      <div className="card-heading"><div><span className="eyebrow">SEC RECORDS</span><h2>Filing history (last 6 months)</h2></div></div>
      <form
        className="research-form sec-records-form"
        onSubmit={(event) => {
          event.preventDefault()
          const ticker = query.trim().toUpperCase()
          if (ticker) onSearch(ticker)
        }}
      >
        <input value={query} onChange={(event) => setQuery(event.target.value.toUpperCase())} placeholder="Search ticker (e.g. AAPL)" />
        <button type="submit" disabled={loading || query.trim().length < 1}>{loading ? 'Loading…' : 'Search'}</button>
      </form>
      {error && <div className="empty-state">{error}</div>}
      {loading && <div className="empty-state">Loading SEC records…</div>}
      {!loading && data && (
        <>
          <div className="sec-records-summary">
            <span>13F: {data.summary['13F'] ?? 0}</span>
            <span>13D: {data.summary['13D'] ?? 0}</span>
            <span>13G: {data.summary['13G'] ?? 0}</span>
            <span>Form 4: {data.summary['4'] ?? 0}</span>
            <span>Since {data.cutoff_date}</span>
          </div>
          {!data.filings.length ? (
            <div className="empty-state">No SEC filings in the last {data.months} months for {data.ticker}.</div>
          ) : (
            <table className="sec-table">
              <thead>
                <tr><th>Filing date</th><th>Form</th><th>Description</th><th>EDGAR</th></tr>
              </thead>
              <tbody>
                {data.filings.map((row) => (
                  <tr key={row.accession_number}>
                    <td>{row.filing_date || '—'}</td>
                    <td>{row.form_type}</td>
                    <td>{row.description}</td>
                    <td>
                      {row.edgar_url ? (
                        <a href={row.edgar_url} target="_blank" rel="noreferrer" className="sec-edgar-link">
                          View <ExternalLink size={14} />
                        </a>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data.insider_transactions.length > 0 && (
            <div className="sec-records-section">
              <h3>Insider transactions</h3>
              <ul>
                {data.insider_transactions.slice(0, 10).map((row, idx) => (
                  <li key={idx}>
                    {String(row.insider)} — {String(row.normalized_type)} ({String(row.transaction_date || row.filing_date || 'n/a')})
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.beneficial_ownership.length > 0 && (
            <div className="sec-records-section">
              <h3>Beneficial ownership</h3>
              <ul>
                {data.beneficial_ownership.slice(0, 10).map((row, idx) => (
                  <li key={idx}>
                    {String(row.reporter)} — {String(row.form_type)} ({String(row.filing_date || 'n/a')})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  )
}
