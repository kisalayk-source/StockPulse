import { ExternalLink, RefreshCw } from 'lucide-react'
import type { GovernmentAnalysisResponse } from './api'
import { formatCurrency, formatDateTime, formatNumber } from './format'

function scoreBarClass(score: number | undefined): string {
  if (score == null) return 'neutral'
  if (score >= 70) return 'positive'
  if (score <= 40) return 'negative'
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

function formatGovValue(value: number | null | undefined): string {
  if (value == null) return '—'
  if (Math.abs(value) >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  return formatCurrency(value)
}

export function GovernmentPanel({
  data,
  loading,
  error,
  onRefresh,
  onSelectTicker,
}: {
  data: GovernmentAnalysisResponse | null
  loading: boolean
  error?: string
  onRefresh?: () => void
  onSelectTicker?: (ticker: string) => void
}) {
  if (loading) {
    return (
      <section className="card sec-card">
        <div className="card-heading">
          <div>
            <span className="eyebrow">GOVERNMENT CONTRACTS</span>
            <h2>Government analysis</h2>
          </div>
        </div>
        <div className="empty-state">Loading government contract data…</div>
      </section>
    )
  }
  if (error) {
    return (
      <section className="card sec-card muted-card">
        <div className="card-heading">
          <div>
            <span className="eyebrow">GOVERNMENT CONTRACTS</span>
            <h2>Government analysis</h2>
          </div>
        </div>
        <div className="empty-state">{error}</div>
      </section>
    )
  }
  if (!data) return null

  const gov = data.government
  const stale = Boolean(data.provider_errors?.length)
  const providerErrors = data.provider_errors || []
  const samSkipped = data.sync?.sam_skipped === 'missing_api_key'
  const exampleTickers = ['BA', 'LMT', 'RTX']
  const showExamples = Boolean(onSelectTicker) && !(data.recent_activity?.length)

  return (
    <section className={`card sec-card${stale ? ' muted-card' : ''}`}>
      <div className="card-heading">
        <div>
          <span className="eyebrow">GOVERNMENT CONTRACTS</span>
          <h2>{data.ticker} government activity</h2>
        </div>
        <div className="agent-controls">
          {onRefresh && (
            <button type="button" className="icon-button" aria-label="Refresh government contracts" onClick={onRefresh}>
              <RefreshCw size={16} />
            </button>
          )}
          <div className={`sec-signal ${gov.score >= 70 ? 'accumulation' : gov.score <= 40 ? 'distribution' : 'neutral'}`}>
            Score {formatNumber(Math.round(gov.score))}
          </div>
        </div>
      </div>

      {data.alerts?.length > 0 && (
        <div className="warning-banner" role="status">
          {data.alerts.map((alert) => (
            <div key={`${alert.type}-${alert.message}`}>{alert.message}</div>
          ))}
        </div>
      )}

      {providerErrors.length > 0 && (
        <div className="warning-banner" role="status">
          {providerErrors.map((row) => (
            <div key={`${row.provider}-${row.message}`}>
              {row.provider}: {row.message}
            </div>
          ))}
        </div>
      )}

      <div className="sec-headline">
        <div>
          <span className="label">Government Score</span>
          <div className="sec-overall-score">
            {formatNumber(Math.round(gov.score))} <small>/ 100</small>
          </div>
        </div>
        <div className="sec-as-of">As of {formatDateTime(data.as_of)}</div>
      </div>

      <ScoreBar label="Early signal" score={gov.early_signal_score} />

      <div className="account-metrics" style={{ marginTop: '0.75rem' }}>
        <div>
          <span>Awards (30d)</span>
          <strong>{formatNumber(gov.awards_30d)}</strong>
        </div>
        <div>
          <span>Award value</span>
          <strong>{formatGovValue(gov.award_value_30d)}</strong>
        </div>
        <div>
          <span>Obligations</span>
          <strong>{formatGovValue(gov.obligation_value_30d)}</strong>
        </div>
        <div>
          <span>Exposure</span>
          <strong>
            {gov.revenue_exposure != null ? `${(gov.revenue_exposure * 100).toFixed(1)}%` : '—'}
          </strong>
        </div>
      </div>

      <div className="activity-section" style={{ marginTop: '1rem' }}>
        <h3>Flags</h3>
        <div className="news-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
          <span>New customer: {gov.new_customer ? 'Yes' : 'No'}</span>
          <span>Sole source: {gov.sole_source ? 'Yes' : 'No'}</span>
          <span>Incumbent: {gov.incumbent ? 'Yes' : 'No'}</span>
          <span>Multi-year: {gov.multi_year ? 'Yes' : 'No'}</span>
        </div>
      </div>

      <div className="activity-section" style={{ marginTop: '1rem' }}>
        <h3>Recent government activity</h3>
        {data.recent_activity?.length ? (
          <div className="activity-list">
            {data.recent_activity.slice(0, 8).map((row, index) => (
              <div className="activity-row" key={`${row.event}-${row.date}-${index}`}>
                <div>
                  <strong>{row.event?.replaceAll('_', ' ')}</strong>
                  <span>
                    {row.date || '—'} · {row.agency || 'Agency n/a'}
                  </span>
                  {row.title && <span>{row.title}</span>}
                </div>
                <div>
                  <strong>{formatGovValue(row.value)}</strong>
                  {row.source_url && (
                    <a href={row.source_url} target="_blank" rel="noreferrer" aria-label="Source">
                      <ExternalLink size={14} />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <div>No contract awards found for {data.ticker}.</div>
            {showExamples && (
              <div className="segmented" style={{ marginTop: '0.75rem' }}>
                {exampleTickers.map((ticker) => (
                  <button key={ticker} type="button" onClick={() => onSelectTicker?.(ticker)}>
                    {ticker}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="activity-section" style={{ marginTop: '1rem' }}>
        <h3>Open opportunities</h3>
        {data.open_opportunities?.length ? (
          <div className="activity-list">
            {data.open_opportunities.slice(0, 5).map((row) => (
              <div className="activity-row" key={row.event_id || `${row.event_type}-${row.title}`}>
                <div>
                  <strong>{(row.event_type || '').replaceAll('_', ' ')}</strong>
                  <span>{row.title || row.solicitation_number || 'Opportunity'}</span>
                </div>
                <div>
                  <strong>{formatGovValue(row.estimated_value ?? row.ceiling_amount)}</strong>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            {samSkipped
              ? 'Open SAM.gov solicitations need SAM_GOV_API_KEY. Awards above still come from USAspending.'
              : `No open opportunities found for ${data.ticker}.`}
          </div>
        )}
      </div>

      <div className="activity-section" style={{ marginTop: '1rem' }}>
        <h3>Top agencies</h3>
        {data.top_agencies?.length ? (
          <div className="activity-list">
            {data.top_agencies.map((row) => (
              <div className="activity-row" key={row.agency}>
                <div>
                  <strong>{row.agency}</strong>
                </div>
                <div>
                  <strong>{formatGovValue(row.value)}</strong>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">No agency exposure yet.</div>
        )}
      </div>

      <p className="disclaimer">
        Government contract data is for research only. Opportunity ceilings are not revenue. Not investment advice.
      </p>
    </section>
  )
}
