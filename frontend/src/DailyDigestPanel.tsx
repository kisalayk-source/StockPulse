import { useEffect, useState } from 'react'
import { LoaderCircle, RefreshCw } from 'lucide-react'
import { api, type DailyDigest } from './api'
import { formatCurrency } from './format'

export function DailyDigestPanel({
  onSelectTicker,
}: {
  onSelectTicker: (ticker: string) => void
}) {
  const [digest, setDigest] = useState<DailyDigest | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      setDigest(await api.dailyDigest())
    } catch (err) {
      setDigest(null)
      setError(err instanceof Error ? err.message : 'Unable to load the daily digest')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <section className="card daily-digest">
      <div className="card-heading">
        <div>
          <span className="eyebrow">TODAY</span>
          <h2>Daily digest</h2>
          <p className="digest-date">{digest ? `${digest.date} · ${digest.timezone}` : 'Insider filings and contract awards'}</p>
        </div>
        <button className="icon-button" type="button" aria-label="Refresh daily digest" onClick={() => void load()}>
          {loading ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
        </button>
      </div>
      {error && <div className="inline-error" role="alert">{error}</div>}
      {loading && !digest ? <div className="loading-state"><LoaderCircle className="spin" size={16} /> Loading stories…</div> : null}
      {!loading && digest && digest.stories.length === 0 ? (
        <div className="empty-state">No insider filings or contract awards for this day.</div>
      ) : null}
      <ol className="digest-list">
        {(digest?.stories || []).map((story) => (
          <li key={`${story.kind}-${story.rank}-${story.ticker || story.title}`}>
            <article>
              <header>
                <span className={`digest-kind ${story.kind}`}>{story.kind}</span>
                <strong>
                  {story.value > 0
                    ? formatCurrency(story.value, true)
                    : (story.amountReason || 'No dollar amount reported')}
                </strong>
              </header>
              <h3>{story.title}</h3>
              <p>{story.summary}</p>
              {story.ticker ? (
                <button type="button" onClick={() => onSelectTicker(story.ticker || '')}>{story.ticker}</button>
              ) : null}
            </article>
          </li>
        ))}
      </ol>
    </section>
  )
}
