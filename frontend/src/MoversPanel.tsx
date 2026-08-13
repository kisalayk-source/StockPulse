import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, LoaderCircle, RefreshCw, Sparkles } from 'lucide-react'
import { api, type Mover, type MoversResponse } from './api'
import { formatCurrency, formatDateTime, formatNumber, formatPercent } from './format'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

function predictedMove(mover: Mover) {
  return mover.netForecastChange ?? mover.forecastChange ?? 0
}

function MoversTable({
  movers,
  empty,
  label,
  onSelectSymbol,
}: {
  movers: Mover[]
  empty: string
  label: string
  onSelectSymbol: (symbol: string) => void
}) {
  if (!movers.length) {
    return <div className="movers-status">{empty}</div>
  }
  return (
    <div className="movers-table-wrap">
      <table className="movers-table">
        <caption className="sr-only">{label}</caption>
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Symbol</th>
            <th scope="col">Last</th>
            <th scope="col">Today</th>
            <th scope="col">Kronos move</th>
            <th scope="col">Target</th>
            <th scope="col">Volume</th>
          </tr>
        </thead>
        <tbody>
          {movers.map((mover, index) => {
            const predicted = predictedMove(mover) >= 0 ? 'positive' : 'negative'
            const today = (mover.dayChange || 0) >= 0 ? 'positive' : 'negative'
            return (
              <tr key={mover.symbol} className={mover.edgeReliable === false ? 'unreliable' : undefined}>
                <td>{index + 1}</td>
                <td>
                  <button type="button" onClick={() => onSelectSymbol(mover.symbol)}>
                    {mover.symbol}
                  </button>
                </td>
                <td>{formatCurrency(mover.lastPrice)}</td>
                <td className={today}>{formatPercent(mover.dayChange, false)}</td>
                <td className={`movers-move ${predicted}`}>
                  {predicted === 'positive' ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
                  {formatPercent(predictedMove(mover), false)}
                </td>
                <td>{formatCurrency(mover.predictedPrice)}</td>
                <td>{formatNumber(mover.volume, true)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function MoversPanel({ onSelectSymbol }: { onSelectSymbol: (symbol: string) => void }) {
  const [state, setState] = useState<LoadState>('idle')
  const [movers, setMovers] = useState<Mover[]>([])
  const [asOf, setAsOf] = useState('')
  const [cached, setCached] = useState(false)
  const [timeframe, setTimeframe] = useState('')
  const [scanned, setScanned] = useState(0)
  const [total, setTotal] = useState(0)
  const [serverGainers, setServerGainers] = useState<Mover[]>([])
  const [serverLosers, setServerLosers] = useState<Mover[]>([])
  const [skipped, setSkipped] = useState(0)
  const [error, setError] = useState('')

  const applyData = useCallback((data: MoversResponse) => {
    setMovers(data.movers)
    setServerGainers(data.gainers || [])
    setServerLosers(data.losers || [])
    setSkipped(data.skipped?.length || 0)
    setAsOf(data.asOf || '')
    setCached(data.cached)
    setTimeframe(data.timeframe || '')
    setScanned(data.scanned)
    setTotal(data.total || data.scanned)
    if (data.status === 'error') {
      setError(data.error || 'Unable to scan movers')
      setState('error')
    } else {
      setState(data.status === 'pending' ? 'loading' : 'ready')
    }
  }, [])

  const load = useCallback(async (refresh = false) => {
    setState('loading')
    setError('')
    try {
      const data = await api.movers(refresh)
      applyData(data)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to scan movers')
      setState('error')
    }
  }, [applyData])

  useEffect(() => {
    void load(false)
  }, [load])

  useEffect(() => {
    if (state !== 'loading') return
    let active = true
    const poll = async () => {
      try {
        const data = await api.moversStatus()
        if (active) applyData(data)
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : 'Unable to check scan progress')
          setState('error')
        }
      }
    }
    const timer = window.setInterval(() => void poll(), 1_500)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [state, applyData])

  const { gainers, losers } = useMemo(() => ({
    gainers: serverGainers.length ? serverGainers : movers.filter((item) => predictedMove(item) >= 0),
    losers: serverLosers.length ? serverLosers : movers.filter((item) => predictedMove(item) < 0),
  }), [movers, serverGainers, serverLosers])

  return (
    <section className="card movers-card" aria-labelledby="movers-title">
      <div className="card-heading">
        <div>
          <span className="eyebrow">STOCKPULSE SCAN</span>
          <h2 id="movers-title">Top 50 potential gainers &amp; losers</h2>
        </div>
        <div className="movers-actions">
          <span className="movers-meta">
            {timeframe ? `${timeframe} horizon` : 'Market-aware scan'}
            {scanned ? ` · ${scanned}${total > scanned ? ` / ${total}` : ''} names` : ''}
            {asOf ? ` · ${cached ? 'Cached' : 'Updated'} ${formatDateTime(asOf)}` : ''}
          </span>
          <button
            className="icon-button"
            aria-label="Refresh predicted movers"
            disabled={state === 'loading'}
            onClick={() => void load(true)}
          >
            {state === 'loading' ? <LoaderCircle className="spin" size={18} /> : <RefreshCw size={18} />}
          </button>
        </div>
      </div>
      {state === 'loading' && movers.length === 0 ? (
        <div className="movers-status">
          <Sparkles size={16} />
          Starting the Kronos scan. Results will appear progressively…
        </div>
      ) : state === 'error' && movers.length === 0 ? (
        <div className="movers-status error">
          {error}
          <button type="button" onClick={() => void load(true)}>Retry</button>
        </div>
      ) : movers.length === 0 ? (
        <div className="movers-status">
          {skipped
            ? `The scan completed, but forecasts were unavailable for ${skipped} or more symbols. Check backend configuration and logs.`
            : 'No predicted movers are available yet.'}
        </div>
      ) : (
        <>
        {state === 'loading' && <div className="scan-progress" role="status">Scanning {scanned} of {total || '…'} names — rankings update automatically.</div>}
        <div className="movers-split">
          <section className="movers-pane">
            <h3>Gainers</h3>
            <MoversTable movers={gainers} empty="No predicted gainers." label="Predicted gainers" onSelectSymbol={onSelectSymbol} />
          </section>
          <section className="movers-pane">
            <h3>Losers</h3>
            <MoversTable movers={losers} empty="No predicted losers." label="Predicted losers" onSelectSymbol={onSelectSymbol} />
          </section>
        </div>
        </>
      )}
      <p className="disclaimer">
        Ranked by absolute Kronos forecast change among today&apos;s most active names, haircut for
        spread and slippage. Dimmed rows have no reliable out-of-sample edge. Display-only — this
        scan never places orders.
      </p>
    </section>
  )
}
