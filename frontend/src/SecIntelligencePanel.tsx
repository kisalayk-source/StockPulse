import { Fragment, useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import type {
  AccumulationScanStatus,
  ResearchQueryResponse,
  SecFilingsAnalysisResponse,
  SecFilingDetail,
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

function insiderTypeLabel(normalizedType: string): string {
  return normalizedType.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())
}

function insiderToneClass(normalizedType: string): string {
  if (normalizedType === 'DISCRETIONARY_BUY') return 'positive'
  if (normalizedType === 'DISCRETIONARY_SELL') return 'negative'
  return 'neutral'
}

function actionToneClass(tone: string | undefined): string {
  if (tone === 'positive') return 'positive'
  if (tone === 'negative') return 'negative'
  return 'neutral'
}

function detailFieldRows(detail: SecFilingDetail): Array<{ label: string; value: string }> {
  const rows: Array<{ label: string; value: string }> = []
  const add = (label: string, value: unknown) => {
    if (value == null || value === '' || value === false) return
    if (typeof value === 'number' && !Number.isFinite(value)) return
    rows.push({ label, value: String(value) })
  }
  add('Role', detail.title)
  add('Transaction date', detail.transaction_date)
  add('Transaction code', detail.transaction_code)
  if (detail.type === 'insider') {
    add('Shares', detail.shares != null ? formatNumber(Math.round(detail.shares)) : null)
    add('Price', detail.price != null ? `$${formatNumber(detail.price)}` : null)
    add('Value', detail.value != null ? `$${formatNumber(Math.round(detail.value))}` : null)
    add('Shares after', detail.shares_owned_after != null ? formatNumber(Math.round(detail.shares_owned_after)) : null)
    add('Ownership', detail.ownership_type)
    add('Derivative', detail.is_derivative ? 'Yes' : null)
  }
  if (detail.type === 'institutional') {
    add('Classification', detail.classification?.replaceAll('_', ' '))
    add('Previous shares', detail.previous_shares != null ? formatNumber(Math.round(detail.previous_shares)) : null)
    add('Current shares', detail.current_shares != null ? formatNumber(Math.round(detail.current_shares)) : null)
    add('Change', detail.change_shares != null ? formatNumber(Math.round(detail.change_shares)) : null)
    add('Change %', detail.change_pct != null ? `${formatNumber(detail.change_pct)}%` : null)
    add('Report period', detail.report_period)
  }
  if (detail.type === 'ownership') {
    add('Issuer', detail.issuer_name)
    add('Ownership %', detail.ownership_pct != null ? `${formatNumber(detail.ownership_pct)}%` : null)
    add('Shares', detail.shares != null ? formatNumber(Math.round(detail.shares)) : null)
    add('Stance', detail.passive === true ? 'Passive' : detail.passive === false ? 'Active' : null)
    add('Purpose', detail.purpose)
  }
  if (detail.type === 'holding') {
    add('Issuer', detail.issuer_name)
    add('Shares held', detail.shares != null ? formatNumber(Math.round(detail.shares)) : null)
    add('Market value', detail.market_value != null ? `$${formatNumber(Math.round(detail.market_value))}` : null)
    add('CUSIP', detail.issuer_cusip)
    add('Security type', detail.security_type)
    add('Put/Call', detail.put_call)
    add('Report period', detail.report_period)
  }
  return rows
}

function FilingDetailsPanel({ details }: { details: SecFilingDetail[] }) {
  if (!details.length) return null
  return (
    <div className="sec-filing-details">
      {details.map((detail, idx) => (
        <div key={idx} className="sec-filing-detail-card">
          <div className="sec-filing-detail-header">
            <strong>{detail.entity}</strong>
            <span className={`sec-band ${actionToneClass(detail.action_tone)}`}>{detail.action}</span>
          </div>
          <dl className="sec-filing-detail-grid">
            {detailFieldRows(detail).map((field) => (
              <div key={field.label} className="sec-filing-detail-item">
                <dt>{field.label}</dt>
                <dd>{field.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  )
}

function sentimentClass(sentiment: SecFilingsAnalysisResponse['sentiment']): string {
  return sentiment
}

function formatInsiderShares(value: unknown): string {
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num) || num === 0) return '—'
  return formatNumber(Math.round(num))
}

function formatInsiderValue(value: unknown): string {
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num) || num === 0) return '—'
  return formatNumber(Math.round(num))
}

function SecRecordsAnalysisCard({
  analysis,
  loading,
  error,
}: {
  analysis: SecFilingsAnalysisResponse | null
  loading: boolean
  error?: string
}) {
  if (loading) {
    return (
      <div className="sec-records-analysis">
        <div className="empty-state">Analyzing filings…</div>
      </div>
    )
  }
  if (error) {
    return (
      <div className="sec-records-analysis muted-card">
        <div className="empty-state">{error}</div>
      </div>
    )
  }
  if (!analysis) return null
  return (
    <div className="sec-records-analysis">
      <div className="sec-records-analysis-header">
        <div>
          <span className="label">AI Analysis</span>
          <h3>{analysis.headline}</h3>
        </div>
        <span className={`sec-sentiment ${sentimentClass(analysis.sentiment)}`}>{analysis.sentiment_label}</span>
      </div>
      <ul className="sec-records-gist">
        {analysis.gist.map((line, idx) => (
          <li key={idx}>{line}</li>
        ))}
      </ul>
      {analysis.highlights.length > 0 && (
        <div className="sec-records-highlights">
          {analysis.highlights.map((item, idx) => (
            <span key={idx} className={`sec-highlight ${item.tone}`}>{item.text}</span>
          ))}
        </div>
      )}
      <div className="sec-records-analysis-meta">
        {analysis.source === 'rules' && analysis.llm_available && !analysis.llm_enabled && (
          <span className="muted">Rule-based analysis — enable <strong>Use AI summaries</strong> in Account settings for LLM summaries</span>
        )}
        {analysis.source === 'rules' && !analysis.llm_available && (
          <span className="muted">Rule-based analysis — AI summaries require server OpenAI configuration</span>
        )}
        {analysis.source === 'rules' && analysis.llm_available && analysis.llm_enabled && (
          <span className="muted">Rule-based analysis — LLM summary unavailable for this filing set</span>
        )}
        <p className="disclaimer">{analysis.disclaimer}</p>
      </div>
    </div>
  )
}

export function SecRecordsPanel({
  symbol,
  data,
  loading,
  error,
  analysis,
  analysisLoading,
  analysisError,
  onSearch,
}: {
  symbol: string
  data: SecFilingsResponse | null
  loading: boolean
  error?: string
  analysis?: SecFilingsAnalysisResponse | null
  analysisLoading?: boolean
  analysisError?: string
  onSearch: (ticker: string) => void
}) {
  const [query, setQuery] = useState(symbol)
  const [expanded, setExpanded] = useState<string | null>(null)
  useEffect(() => { setQuery(symbol) }, [symbol])
  useEffect(() => { setExpanded(null) }, [data?.ticker])

  const statItems = [
    { label: '13F', key: '13F', hint: 'Institutional' },
    { label: '13D', key: '13D', hint: 'Active ownership' },
    { label: '13G', key: '13G', hint: 'Passive ownership' },
    { label: 'Form 4', key: '4', hint: 'Insider trades' },
  ]

  return (
    <section className="card sec-card">
      <div className="card-heading">
        <div>
          <span className="eyebrow">SEC RECORDS</span>
          <h2>Filing history (last 6 months)</h2>
        </div>
      </div>
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
          {(analysisLoading || analysis || analysisError) && (
            <SecRecordsAnalysisCard
              analysis={analysis ?? null}
              loading={Boolean(analysisLoading)}
              error={analysisError}
            />
          )}
          {data.provider_errors && data.provider_errors.length > 0 && (
            <div className="sec-records-warnings">
              {data.provider_errors.map((item, idx) => (
                <div key={idx} className="empty-state">{item.provider}: {item.message}</div>
              ))}
            </div>
          )}
          <div className="sec-stat-grid">
            {statItems.map((item) => (
              <div key={item.key} className="sec-stat-chip">
                <span className="sec-stat-value">{data.summary[item.key] ?? 0}</span>
                <span className="sec-stat-label">{item.label}</span>
                <span className="sec-stat-hint">{item.hint}</span>
              </div>
            ))}
            <div className="sec-stat-chip muted">
              <span className="sec-stat-label">Since</span>
              <span className="sec-stat-value">{data.cutoff_date}</span>
            </div>
          </div>
          {!data.filings.length ? (
            <div className="empty-state">No SEC filings in the last {data.months} months for {data.ticker}.</div>
          ) : (
            <table className="sec-table sec-records-filings-table">
              <thead>
                <tr><th aria-hidden="true" /><th>Filing date</th><th>Form</th><th>Filing entity</th><th>Action</th><th>EDGAR</th></tr>
              </thead>
              <tbody>
                {data.filings.map((row) => {
                  const isOpen = expanded === row.accession_number
                  const hasDetails = Boolean(row.details?.length)
                  return (
                    <Fragment key={row.accession_number}>
                      <tr
                        key={row.accession_number}
                        className={hasDetails ? 'sec-filing-row expandable' : 'sec-filing-row'}
                        onClick={() => {
                          if (!hasDetails) return
                          setExpanded(isOpen ? null : row.accession_number)
                        }}
                      >
                        <td className="sec-filing-expand">
                          {hasDetails ? (
                            <button
                              type="button"
                              className="sec-filing-expand-btn"
                              aria-expanded={isOpen}
                              aria-label={isOpen ? 'Hide parsed filing details' : 'Show parsed filing details'}
                              onClick={(event) => {
                                event.stopPropagation()
                                setExpanded(isOpen ? null : row.accession_number)
                              }}
                            >
                              {isOpen ? '−' : '+'}
                            </button>
                          ) : null}
                        </td>
                        <td>{row.filing_date ? formatDateTime(row.filing_date) : '—'}</td>
                        <td>
                          <span className={`sec-type-badge ${row.form_family.toLowerCase().replace(/\s/g, '')}`}>
                            {row.form_type}
                          </span>
                          {row.is_amendment && <span className="sec-amendment-badge">Amendment</span>}
                          {row.report_period && <span className="sec-report-period">Period {row.report_period}</span>}
                        </td>
                        <td className="sec-filer-cell">{row.filer_name || '—'}</td>
                        <td>
                          {row.action ? (
                            <span className={`sec-band ${actionToneClass(row.action_tone)}`}>{row.action}</span>
                          ) : '—'}
                        </td>
                        <td>
                          {row.edgar_url ? (
                            <a href={row.edgar_url} target="_blank" rel="noreferrer" className="sec-edgar-link" onClick={(event) => event.stopPropagation()}>
                              View <ExternalLink size={14} />
                            </a>
                          ) : '—'}
                        </td>
                      </tr>
                      {isOpen && hasDetails && (
                        <tr key={`${row.accession_number}-details`} className="sec-filing-details-row">
                          <td colSpan={6}>
                            <FilingDetailsPanel details={row.details || []} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          )}
          {data.insider_transactions.length > 0 && (
            <div className="sec-records-section">
              <h3>Insider transactions</h3>
              <table className="sec-table sec-records-mini-table">
                <thead>
                  <tr><th>Insider</th><th>Role</th><th>Action</th><th>Date</th><th>Shares</th><th>Value</th></tr>
                </thead>
                <tbody>
                  {data.insider_transactions.slice(0, 10).map((row, idx) => {
                    const actionTone = String(row.action_tone || insiderToneClass(String(row.normalized_type || '')))
                    const actionLabel = String(row.action || insiderTypeLabel(String(row.normalized_type || '')))
                    return (
                      <tr key={idx}>
                        <td>{String(row.insider)}</td>
                        <td>{String(row.title || '—')}</td>
                        <td>
                          <span className={`sec-band ${actionToneClass(actionTone)}`}>
                            {actionLabel}
                          </span>
                        </td>
                        <td>{String(row.transaction_date || row.filing_date || '—')}</td>
                        <td>{formatInsiderShares(row.shares)}</td>
                        <td>{formatInsiderValue(row.value)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          {data.beneficial_ownership.length > 0 && (
            <div className="sec-records-section">
              <h3>Beneficial ownership</h3>
              <table className="sec-table sec-records-mini-table">
                <thead>
                  <tr><th>Reporter</th><th>Form</th><th>Action</th><th>Ownership</th><th>Stance</th><th>Filed</th></tr>
                </thead>
                <tbody>
                  {data.beneficial_ownership.slice(0, 10).map((row, idx) => (
                    <tr key={idx}>
                      <td>{String(row.reporter)}</td>
                      <td><span className="sec-type-badge">{String(row.form_type)}</span></td>
                      <td>
                        <span className={`sec-band ${actionToneClass(String(row.action_tone || 'neutral'))}`}>
                          {String(row.action || row.event_type || 'Ownership filing')}
                        </span>
                      </td>
                      <td>{row.ownership_pct != null ? `${formatNumber(Number(row.ownership_pct))}%` : '—'}</td>
                      <td>
                        <span className={`sec-band ${row.passive ? 'neutral' : 'positive'}`}>
                          {row.passive ? 'Passive' : 'Active'}
                        </span>
                      </td>
                      <td>{String(row.filing_date || '—')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}
