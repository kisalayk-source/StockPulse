import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  OctagonX,
  Pause,
  Play,
  RefreshCw,
  ShieldAlert,
  Square,
  X,
} from 'lucide-react'
import {
  ApiError,
  api,
  type AgentEventRow,
  type AgentOrderRow,
  type AgentPerformance,
  type AgentPositionRow,
  type AgentTradingType,
  type DailyLossState,
  type DayTradesReport,
  type RiskProfile,
  type TradeCandidateRow,
  type TradingAgentConfig,
  type UniverseScanRow,
} from './api'
import { formatCurrency, formatDateTime, formatPercent } from './format'

function statusLabel(status: string): string {
  switch (status) {
    case 'paper':
      return 'Paper Trading'
    case 'live':
      return 'Live Trading'
    case 'paused':
      return 'Paused'
    case 'emergency_stop':
      return 'Emergency Stop'
    case 'configured':
      return 'Configured'
    default:
      return 'Disabled'
  }
}

function dailyLossClass(status: string): string {
  if (status === 'blocked') return 'daily-loss-card blocked'
  if (status === 'critical') return 'daily-loss-card critical'
  if (status === 'warning') return 'daily-loss-card warning'
  return 'daily-loss-card'
}

const TICKER_PATTERN = /^[A-Z][A-Z0-9.-]{0,9}$/

function parseTickers(raw: string): string[] {
  const seen = new Set<string>()
  const tickers: string[] = []
  for (const part of raw.split(/[\s,;]+/)) {
    const ticker = part.trim().toUpperCase()
    if (!ticker || seen.has(ticker)) continue
    seen.add(ticker)
    tickers.push(ticker)
  }
  return tickers
}

function mergeUniverse(current: string[], extra: string[]): string[] {
  const seen = new Set(current)
  const next = [...current]
  for (const ticker of extra) {
    if (seen.has(ticker)) continue
    seen.add(ticker)
    next.push(ticker)
  }
  return next
}

function todayInAgentTz(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' }).format(new Date())
}

function sessionDayInAgentTz(iso: string | null | undefined): string | null {
  if (!iso) return null
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) {
    const prefix = iso.slice(0, 10)
    return /^\d{4}-\d{2}-\d{2}$/.test(prefix) ? prefix : null
  }
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' }).format(parsed)
}

function latestFillSessionDay(orders: AgentOrderRow[]): string | null {
  let best: string | null = null
  for (const row of orders) {
    if (row.status !== 'filled' && row.status !== 'partially_filled') continue
    const day = sessionDayInAgentTz(row.filledAt || row.submittedAt)
    if (day && (!best || day > best)) best = day
  }
  return best
}

const MAX_UNIVERSE_FALLBACK = 50

function scanOutcomeLabel(outcome: string): string {
  switch (outcome) {
    case 'approved':
      return 'Approved'
    case 'risk_rejected':
      return 'Risk rejected'
    case 'hold':
      return 'Hold'
    case 'unavailable':
      return 'Unavailable'
    case 'forecast_error':
      return 'Forecast error'
    case 'qty_zero':
      return 'Size zero'
    case 'no_price':
      return 'No price'
    case 'no_position':
      return 'No position'
    case 'skipped':
      return 'Skipped'
    default:
      return outcome || '—'
  }
}

function csvCell(value: string | number | null | undefined): string {
  const raw = value == null ? '' : String(value)
  if (/[",\n]/.test(raw)) return `"${raw.replaceAll('"', '""')}"`
  return raw
}

function downloadDayTradesCsv(report: DayTradesReport) {
  const header = ['time', 'symbol', 'side', 'qty', 'entry', 'exit_or_mark', 'pnl', 'result', 'status']
  const rows = report.trades.map((row) => [
    csvCell(row.filledAt),
    csvCell(row.symbol),
    csvCell(row.side),
    csvCell(row.quantity),
    csvCell(row.entryPrice),
    csvCell(row.exitPrice),
    csvCell(row.pnl),
    csvCell(row.result),
    csvCell(row.status),
  ].join(','))
  const blob = new Blob([`${header.join(',')}\n${rows.join('\n')}\n`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `day-trades-${report.date}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function TradingAgentPanel({
  onOpenRiskSettings,
}: {
  onOpenRiskSettings?: () => void
}) {
  const [config, setConfig] = useState<TradingAgentConfig | null>(null)
  const [candidates, setCandidates] = useState<TradeCandidateRow[]>([])
  const [positions, setPositions] = useState<AgentPositionRow[]>([])
  const [orders, setOrders] = useState<AgentOrderRow[]>([])
  const [events, setEvents] = useState<AgentEventRow[]>([])
  const [performance, setPerformance] = useState<AgentPerformance | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [livePhrase, setLivePhrase] = useState('')
  const [capital, setCapital] = useState('')
  const [cycleMinutes, setCycleMinutes] = useState('5')
  const [maxLossAmount, setMaxLossAmount] = useState('')
  const [maxLossPercent, setMaxLossPercent] = useState('')
  const [tickerInput, setTickerInput] = useState('')
  const [dayTradeDate, setDayTradeDate] = useState(todayInAgentTz)
  const [dayTrades, setDayTrades] = useState<DayTradesReport | null>(null)
  const [dayTradesBusy, setDayTradesBusy] = useState(false)
  const dayTradeDateTouchedRef = useRef(false)

  const applyConfig = useCallback((next: TradingAgentConfig) => {
    setConfig(next)
    setCapital(String(next.capitalAllocation || ''))
    setCycleMinutes(String(Math.max(1, Math.round((next.cycleIntervalSeconds || 300) / 60))))
    const amount = next.riskConfig.max_daily_loss_amount
    const pct = next.riskConfig.max_daily_loss_percent
    setMaxLossAmount(amount != null ? String(amount) : '')
    setMaxLossPercent(pct != null ? String(pct) : '')
  }, [])

  const refresh = useCallback(async () => {
    setError('')
    try {
      const cfg = await api.getTradingAgentConfig()
      applyConfig(cfg)
      const [cands, pos, ords, evts, perf] = await Promise.all([
        api.getTradingAgentCandidates(),
        api.getTradingAgentPositions(),
        api.getTradingAgentOrders(),
        api.getTradingAgentEvents(),
        api.getTradingAgentPerformance(),
      ])
      setCandidates(cands)
      setPositions(pos)
      setOrders(ords)
      setEvents(evts)
      setPerformance(perf)
      if (!dayTradeDateTouchedRef.current) {
        const latest = latestFillSessionDay(ords)
        if (latest) setDayTradeDate(latest)
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load trading agent')
    }
  }, [applyConfig])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const running = config?.status === 'paper' || config?.status === 'live'

  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => {
      void refresh()
    }, 15_000)
    return () => window.clearInterval(timer)
  }, [running, refresh])

  async function run(action: () => Promise<unknown>, success?: string) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await action()
      if (success) setNotice(success)
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  async function saveUniverse(next: string[], success = 'Risk portfolio updated') {
    const maxSize = config?.maxUniverseSize || MAX_UNIVERSE_FALLBACK
    const unique = [...new Set(next.map((ticker) => ticker.toUpperCase()).filter(Boolean))]
    const invalid = unique.find((ticker) => !TICKER_PATTERN.test(ticker))
    if (invalid) {
      setError(`Invalid ticker: ${invalid}`)
      return
    }
    if (unique.length === 0) {
      setError('Risk portfolio must include at least one ticker')
      return
    }
    if (unique.length > maxSize) {
      setError(`Risk portfolio cannot exceed ${maxSize} tickers`)
      return
    }
    await run(() => api.updateTradingAgentConfig({ universe: unique }), success)
  }

  async function addTickers() {
    const extra = parseTickers(tickerInput)
    if (extra.length === 0) return
    setTickerInput('')
    await saveUniverse(mergeUniverse(config?.universe || [], extra))
  }

  async function generateDayTrades(explicitDate?: string) {
    const requested = explicitDate || dayTradeDate || undefined
    setDayTradesBusy(true)
    setError('')
    setNotice('')
    try {
      let report = await api.getTradingAgentDayTrades(requested)
      if (
        report.trades.length === 0
        && report.latestDate
        && report.latestDate !== report.date
        && !explicitDate
      ) {
        setDayTradeDate(report.latestDate)
        setNotice(`No fills on ${report.date}; showing latest session ${report.latestDate}`)
        report = await api.getTradingAgentDayTrades(report.latestDate)
      }
      setDayTrades(report)
      if (report.latestDate && !dayTradeDateTouchedRef.current) {
        setDayTradeDate(report.date)
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to generate day trades')
    } finally {
      setDayTradesBusy(false)
    }
  }

  async function removeTicker(symbol: string) {
    await saveUniverse((config?.universe || []).filter((ticker) => ticker !== symbol))
  }

  async function importFavorites() {
    setError('')
    setNotice('')
    setBusy(true)
    let extra: string[] = []
    try {
      const favorites = await api.listFavorites()
      extra = favorites.map((row) => row.ticker).filter(Boolean)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load favorites')
      setBusy(false)
      return
    }
    setBusy(false)
    if (extra.length === 0) {
      setNotice('No favorites to sync')
      return
    }
    const merged = mergeUniverse(config?.universe || [], extra)
    const maxSize = config?.maxUniverseSize || MAX_UNIVERSE_FALLBACK
    if (merged.length > maxSize) {
      setError(
        `Favorites sync would exceed ${maxSize} tickers (${merged.length}). Remove some favorites or portfolio tickers first.`,
      )
      return
    }
    const added = merged.length - (config?.universe || []).length
    await saveUniverse(
      merged,
      added > 0
        ? `Synced favorites · added ${added} ticker${added === 1 ? '' : 's'}`
        : 'Risk portfolio already includes all favorites',
    )
  }

  const daily: DailyLossState | undefined = config?.dailyLoss
  const intervalMinutes = Math.max(1, Math.round((config?.cycleIntervalSeconds || 300) / 60))
  const autoCycleLabel = running
    ? `Auto-cycling every ${intervalMinutes}m${
        config?.lastCycleAt ? ` · last cycle ${formatDateTime(config.lastCycleAt)}` : ' · waiting for first cycle'
      }`
    : null
  const accepted = candidates.filter((row) => row.status === 'approved')
  const rejected = candidates.filter((row) => row.status === 'rejected')
  const riskAdjustEvents = events.filter(
    (event) => event.eventType === 'RISK_AUTO_ADJUSTED' || event.eventType === 'RISK_AUTO_ADJUST_SKIPPED',
  )
  const latestRiskAdjust = riskAdjustEvents[0]
  const filledOrders = orders.filter((row) => row.status === 'filled' || row.status === 'partially_filled')
  const universeScan: UniverseScanRow[] = config?.lastUniverseScan || []
  const maxUniverseSize = config?.maxUniverseSize || MAX_UNIVERSE_FALLBACK
  const universeCount = (config?.universe || []).length
  const cycleNotice =
    running && accepted.length === 0 && rejected.length > 0
      ? latestRiskAdjust?.message ||
        `Latest cycle rejected ${rejected.length} opportunities with no approvals. Risk may auto-adjust for the next cycle.`
      : null

  return (
    <div className="trading-agent-page" data-testid="trading-agent-page">
      <section className="card agent-hero">
        <div className="card-heading">
          <div>
            <p className="label">Autonomous Trading Agent</p>
            <h2>Status: {statusLabel(config?.status || 'disabled')}</h2>
            <p className="agent-subtitle">
              Forecast Mode: {config?.forecastEnabled ? 'Enabled' : 'Disabled'} · Mode:{' '}
              {(config?.mode || 'paper').toUpperCase()}
              {config?.liveTradingEnabled ? ' · Live armed' : ''}
            </p>
            {autoCycleLabel && <p className="agent-subtitle">{autoCycleLabel}</p>}
          </div>
          <div className="agent-controls">
            <button
              type="button"
              disabled={busy || running}
              onClick={() => void run(() => api.startTradingAgent('paper'), 'Agent started (paper)')}
            >
              <Play size={14} /> Start Agent
            </button>
            <button
              type="button"
              disabled={busy || !running}
              onClick={() => void run(() => api.pauseTradingAgent(), 'Agent paused')}
            >
              <Pause size={14} /> Pause
            </button>
            <button
              type="button"
              disabled={busy || config?.status !== 'paused'}
              onClick={() => void run(() => api.resumeTradingAgent(), 'Agent resumed')}
            >
              <Play size={14} /> Resume
            </button>
            <button
              type="button"
              className="danger"
              disabled={busy}
              onClick={() => void run(() => api.emergencyStopTradingAgent(), 'Emergency stop engaged')}
            >
              <OctagonX size={14} /> Emergency Stop
            </button>
            <button type="button" disabled={busy} onClick={() => void refresh()} aria-label="Refresh agent">
              <RefreshCw size={14} />
            </button>
          </div>
        </div>

        {error && (
          <div className="error-banner compact">
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}
        {notice && <p className="settings-notice">{notice}</p>}
        {cycleNotice && (
          <div className="warning-banner compact" role="status" data-testid="cycle-reject-notice">
            <AlertTriangle size={16} />
            <span>{cycleNotice}</span>
          </div>
        )}
        {config?.status === 'live' && (
          <div className="danger-callout" role="alert">
            <ShieldAlert size={16} />
            Live trading is active. Orders may be submitted to your broker.
          </div>
        )}
      </section>

      <section className={dailyLossClass(daily?.status || 'active')} data-testid="max-daily-loss">
        <div className="card-heading compact">
          <div>
            <h2>Max Daily Loss</h2>
            <p className="agent-subtitle">Enforced by the backend risk engine for all trading modes</p>
          </div>
          <span className={`status daily-status ${daily?.status || 'active'}`}>
            {daily?.limitReached ? 'Blocked' : daily?.status || 'active'}
          </span>
        </div>
        <div className="daily-loss-grid">
          <label>
            <span>Enable Max Daily Loss</span>
            <input
              type="checkbox"
              checked={Boolean(config?.riskConfig.max_daily_loss_enabled ?? true)}
              disabled={busy}
              onChange={(event) =>
                void run(
                  () => api.updateTradingAgentDailyLoss({ max_daily_loss_enabled: event.target.checked }),
                  'Daily loss setting updated',
                )
              }
            />
          </label>
          <label>
            <span>Maximum loss today ($)</span>
            <input
              type="number"
              value={maxLossAmount}
              disabled={busy}
              onChange={(event) => setMaxLossAmount(event.target.value)}
              onBlur={() => {
                const value = Number(maxLossAmount)
                if (!Number.isFinite(value)) return
                void run(
                  () => api.updateTradingAgentDailyLoss({ max_daily_loss_amount: value }),
                  'Max daily loss amount saved',
                )
              }}
            />
          </label>
          <label>
            <span>% of starting daily equity</span>
            <input
              type="number"
              step="0.01"
              value={maxLossPercent}
              disabled={busy}
              onChange={(event) => setMaxLossPercent(event.target.value)}
              onBlur={() => {
                const value = Number(maxLossPercent)
                if (!Number.isFinite(value)) return
                void run(
                  () => api.updateTradingAgentDailyLoss({ max_daily_loss_percent: value }),
                  'Max daily loss percent saved',
                )
              }}
            />
          </label>
          <div>
            <span className="label">Today&apos;s P/L</span>
            <strong className={(daily?.todayPnl || 0) < 0 ? 'negative' : 'positive'}>
              {formatCurrency(daily?.todayPnl)} / {formatCurrency(daily?.effectiveLimit != null ? -daily.effectiveLimit : null)}
            </strong>
          </div>
          <div>
            <span className="label">Remaining daily loss</span>
            <strong>{formatCurrency(daily?.remainingDailyLoss)}</strong>
          </div>
          <div>
            <span className="label">Utilization</span>
            <strong>{formatPercent((daily?.utilizationPct || 0) / 100)}</strong>
          </div>
          <div data-testid="day-trades-today">
            <span className="label">Day trades today</span>
            <strong>
              {daily?.maxTradesPerDay != null && daily.maxTradesPerDay > 0
                ? `${daily.tradesToday ?? 0} / ${daily.maxTradesPerDay}`
                : '—'}
            </strong>
          </div>
        </div>
        {daily?.warnings?.length ? (
          <div className="warning-banner compact" role="status">
            <AlertTriangle size={16} />
            <span>{daily.warnings.join(' · ')}</span>
          </div>
        ) : null}
        {daily?.limitReached ? (
          <div className="danger-callout" data-testid="daily-loss-blocked">
            <Square size={16} />
            New trades are blocked. Reset daily loss or wait for the next reset, then resume explicitly.
            <button
              type="button"
              disabled={busy}
              onClick={() => void run(() => api.resetTradingAgentDailyLoss(), 'Daily loss reset')}
            >
              Reset daily loss
            </button>
          </div>
        ) : null}
      </section>

      <section className="card agent-settings">
        <div className="card-heading compact">
          <h2>Agent configuration</h2>
          <button type="button" className="text-button" onClick={onOpenRiskSettings}>
            Risk management settings
          </button>
        </div>
        <div className="agent-config-grid">
          <div>
            <span className="label">Trading Mode</span>
            <div className="mode-chips" role="group" aria-label="Trading mode">
              {(['options', 'day_trading', 'long_term', 'mixed'] as AgentTradingType[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={config?.tradingType === mode ? 'active' : ''}
                  disabled={busy}
                  onClick={() =>
                    void run(
                      () => api.updateTradingAgentConfig({ trading_type: mode }),
                      `Trading mode: ${mode}`,
                    )
                  }
                >
                  {mode === 'day_trading' ? 'Day Trading' : mode === 'long_term' ? 'Long Term' : mode[0].toUpperCase() + mode.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <label>
            <span>Risk Profile</span>
            <select
              value={config?.riskProfile || 'medium'}
              disabled={busy}
              onChange={(event) =>
                void run(
                  () => api.updateTradingAgentConfig({ risk_profile: event.target.value as RiskProfile }),
                  'Risk profile updated',
                )
              }
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          <label>
            <span>Capital Allocation</span>
            <input
              type="number"
              value={capital}
              disabled={busy}
              onChange={(event) => setCapital(event.target.value)}
              onBlur={() => {
                const value = Number(capital)
                if (!Number.isFinite(value) || value <= 0) return
                void run(
                  () => api.updateTradingAgentConfig({ capital_allocation: value }),
                  'Capital allocation saved',
                )
              }}
            />
          </label>
          <div className="universe-editor" data-testid="risk-portfolio">
            <span>Risk portfolio</span>
            <p className="agent-subtitle">
              Symbols the agent forecasts and trades each cycle ({universeCount} / {maxUniverseSize}).
              Sync favorites to cover your full watchlist.
            </p>
            <div className="universe-chips" role="list" aria-label="Risk portfolio tickers">
              {!config ? (
                <span className="agent-subtitle">Loading…</span>
              ) : (config.universe || []).length === 0 ? (
                <span className="agent-subtitle">No tickers yet</span>
              ) : (
                (config.universe || []).map((ticker) => (
                  <span key={ticker} className="universe-chip" role="listitem">
                    {ticker}
                    <button
                      type="button"
                      className="universe-chip-remove"
                      aria-label={`Remove ${ticker} from risk portfolio`}
                      disabled={busy || (config?.universe || []).length <= 1}
                      onClick={() => void removeTicker(ticker)}
                    >
                      <X size={12} />
                    </button>
                  </span>
                ))
              )}
            </div>
            <div className="inline-fields">
              <input
                value={tickerInput}
                disabled={busy}
                placeholder="Add tickers (AAPL, MSFT)"
                aria-label="Add tickers to risk portfolio"
                onChange={(event) => setTickerInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void addTickers()
                  }
                }}
              />
              <button type="button" disabled={busy || !parseTickers(tickerInput).length} onClick={() => void addTickers()}>
                Add
              </button>
              <button type="button" disabled={busy} onClick={() => void importFavorites()}>
                Sync favorites
              </button>
            </div>
          </div>
          <label>
            <span>Auto-cycle interval (minutes)</span>
            <input
              type="number"
              min={1}
              max={1440}
              value={cycleMinutes}
              disabled={busy}
              onChange={(event) => setCycleMinutes(event.target.value)}
              onBlur={() => {
                const minutes = Number(cycleMinutes)
                if (!Number.isFinite(minutes) || minutes < 1) return
                const seconds = Math.round(minutes) * 60
                void run(
                  () => api.updateTradingAgentConfig({ cycle_interval_seconds: seconds }),
                  `Auto-cycle every ${Math.round(minutes)}m`,
                )
              }}
            />
          </label>
          <label>
            <span>Enable live trading (type LIVE)</span>
            <div className="inline-fields">
              <input
                value={livePhrase}
                onChange={(event) => setLivePhrase(event.target.value)}
                placeholder="LIVE"
                disabled={busy || Boolean(config?.liveTradingEnabled)}
              />
              <button
                type="button"
                disabled={busy || Boolean(config?.liveTradingEnabled)}
                onClick={() =>
                  void run(
                    () =>
                      api.updateTradingAgentConfig({
                        live_trading_enabled: true,
                        live_confirmation: livePhrase,
                      }),
                    'Live trading enabled',
                  )
                }
              >
                Arm live
              </button>
            </div>
          </label>
          <button
            type="button"
            disabled={busy || !running}
            onClick={() => void run(() => api.runTradingAgentCycle(config?.universe, true), 'Cycle complete')}
          >
            Run forecast cycle
          </button>
        </div>
      </section>

      <div className="agent-panels">
        <section className="card agent-resizable" data-testid="universe-scan">
          <div className="card-heading compact">
            <h2>Universe scan</h2>
            <p className="agent-subtitle">
              Last cycle outcome for every risk-portfolio ticker
              {config?.lastCycleAt ? ` · ${formatDateTime(config.lastCycleAt)}` : ''}
            </p>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Outcome</th>
                  <th>Signal</th>
                  <th>Confidence</th>
                  <th>Mark</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {universeScan.length === 0 ? (
                  <tr><td colSpan={6}>Run a forecast cycle to see per-symbol scan results</td></tr>
                ) : universeScan.map((row) => (
                  <tr key={row.symbol}>
                    <td>{row.symbol}</td>
                    <td>{scanOutcomeLabel(row.outcome)}</td>
                    <td>{row.signal || '—'}</td>
                    <td>{formatPercent(row.confidence ?? null)}</td>
                    <td>{row.price != null ? formatCurrency(row.price) : '—'}</td>
                    <td className="agent-reject-reason">{row.reason || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card agent-resizable" data-testid="accepted-queue">
          <div className="card-heading compact">
            <h2>Accepted opportunities</h2>
            <p className="agent-subtitle">Recent approved entries and exits (not limited by reject volume)</p>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Strategy</th>
                  <th>Signal</th>
                  <th>Reason</th>
                  <th>Confidence</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {accepted.length === 0 ? (
                  <tr><td colSpan={7}>No approved opportunities this cycle window</td></tr>
                ) : accepted.map((row) => (
                  <tr key={row.id}>
                    <td>{row.symbol}</td>
                    <td>{row.side || '—'}</td>
                    <td>{row.strategy}</td>
                    <td>{String(row.forecastSnapshot.signal || '—')}</td>
                    <td>{row.exitReason ? String(row.exitReason).replaceAll('_', ' ') : '—'}</td>
                    <td>{formatPercent(Number(row.forecastSnapshot.confidence) || null)}</td>
                    <td>{formatDateTime(row.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card agent-resizable" data-testid="rejected-queue">
          <div className="card-heading compact"><h2>Rejected opportunities</h2></div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Strategy</th>
                  <th>Signal</th>
                  <th>Confidence</th>
                  <th>Reason</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {rejected.length === 0 ? (
                  <tr><td colSpan={6}>No rejections yet</td></tr>
                ) : rejected.map((row) => (
                  <tr key={row.id}>
                    <td>{row.symbol}</td>
                    <td>{row.strategy}</td>
                    <td>{String(row.forecastSnapshot.signal || '—')}</td>
                    <td>{formatPercent(Number(row.forecastSnapshot.confidence) || null)}</td>
                    <td className="agent-reject-reason">
                      {String(row.riskDecision?.reason || 'Rejected by risk engine')}
                    </td>
                    <td>{formatDateTime(row.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card agent-resizable" data-testid="active-positions">
          <div className="card-heading compact"><h2>Active Positions</h2></div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Entry</th>
                  <th>Invested</th>
                  <th>Mark</th>
                  <th>Unrealized</th>
                </tr>
              </thead>
              <tbody>
                {positions.length === 0 ? (
                  <tr><td colSpan={6}>No open agent positions</td></tr>
                ) : positions.map((row) => (
                  <tr key={row.id}>
                    <td>{row.symbol}</td>
                    <td>{row.quantity}</td>
                    <td>{formatCurrency(row.averageEntryPrice)}</td>
                    <td>{formatCurrency(row.quantity * row.averageEntryPrice)}</td>
                    <td>{formatCurrency(row.currentPrice)}</td>
                    <td className={row.unrealizedPnl < 0 ? 'negative' : 'positive'}>{formatCurrency(row.unrealizedPnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card agent-resizable" data-testid="trade-history">
          <div className="card-heading compact">
            <h2>Trade History</h2>
            <p className="agent-subtitle">
              Filled &amp; submitted agent orders · {filledOrders.length} filled
              {performance?.numberOfTrades != null ? ` · Performance trades ${performance.numberOfTrades}` : ''}
            </p>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Fill</th>
                  <th>Status</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {orders.length === 0 ? (
                  <tr><td colSpan={6}>No agent orders yet</td></tr>
                ) : orders.map((row) => (
                  <tr key={row.id}>
                    <td>{row.symbol}</td>
                    <td>{row.side}</td>
                    <td>{row.filledQuantity || row.requestedQuantity}</td>
                    <td>{formatCurrency(row.averageFillPrice)}</td>
                    <td><span className={`status ${row.status}`}>{row.status}</span></td>
                    <td>{formatDateTime(row.filledAt || row.submittedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card agent-resizable" data-testid="daily-trades">
          <div className="card-heading compact">
            <h2>Daily trades</h2>
            <p className="agent-subtitle">
              Session-day fills labeled profit or loss using average cost
              {dayTrades?.timezone ? ` · ${dayTrades.timezone}` : ''}
            </p>
          </div>
          <div className="daily-trades-toolbar">
            <label>
              Session day
              <input
                type="date"
                value={dayTradeDate}
                onChange={(event) => {
                  dayTradeDateTouchedRef.current = true
                  setDayTradeDate(event.target.value)
                }}
                aria-label="Session day"
              />
            </label>
            <div className="agent-controls">
              <button type="button" disabled={dayTradesBusy} onClick={() => void generateDayTrades()}>
                Generate
              </button>
              <button
                type="button"
                disabled={!dayTrades}
                onClick={() => dayTrades && downloadDayTradesCsv(dayTrades)}
              >
                Download CSV
              </button>
            </div>
          </div>
          {dayTrades ? (
            <p className="daily-trades-summary" data-testid="daily-trades-summary">
              {dayTrades.summary.wins} wins · {dayTrades.summary.losses} losses
              {dayTrades.summary.open ? ` · ${dayTrades.summary.open} open` : ''}
              {' · '}net realized {formatCurrency(dayTrades.summary.netRealizedPnl)}
            </p>
          ) : (
            <p className="daily-trades-summary">Choose a day and generate the session P/L report.</p>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Entry</th>
                  <th>Exit / mark</th>
                  <th>P/L</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {!dayTrades ? (
                  <tr><td colSpan={8}>No report generated yet</td></tr>
                ) : dayTrades.trades.length === 0 ? (
                  <tr>
                    <td colSpan={8}>
                      No agent trades on {dayTrades.date}
                      {dayTrades.latestDate && dayTrades.latestDate !== dayTrades.date ? (
                        <>
                          {' · '}
                          <button
                            type="button"
                            className="text-button"
                            disabled={dayTradesBusy}
                            onClick={() => {
                              dayTradeDateTouchedRef.current = true
                              setDayTradeDate(dayTrades.latestDate!)
                              void generateDayTrades(dayTrades.latestDate!)
                            }}
                          >
                            Open latest session {dayTrades.latestDate}
                          </button>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ) : dayTrades.trades.map((row) => (
                  <tr key={`${row.status}-${row.id}`}>
                    <td>{formatDateTime(row.filledAt)}</td>
                    <td>{row.symbol}</td>
                    <td>{row.side}</td>
                    <td>{row.quantity}</td>
                    <td>{formatCurrency(row.entryPrice)}</td>
                    <td>{formatCurrency(row.exitPrice)}</td>
                    <td className={row.pnl < 0 ? 'negative' : row.pnl > 0 ? 'positive' : undefined}>
                      {formatCurrency(row.pnl)}
                    </td>
                    <td>{row.result}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card agent-resizable" data-testid="risk-auto-adjust-log">
          <div className="card-heading compact"><h2>Risk auto-adjustments</h2></div>
          <ul className="agent-log">
            {riskAdjustEvents.length === 0 ? (
              <li>No automatic risk changes yet. When a cycle rejects every opportunity, thresholds may loosen and appear here.</li>
            ) : riskAdjustEvents.map((event) => (
              <li key={event.id} className={`severity-${event.severity}`}>
                <strong>{event.eventType === 'RISK_AUTO_ADJUSTED' ? 'Risk loosened' : 'Adjust skipped'}</strong>
                <span>{event.message}</span>
                <small>{formatDateTime(event.createdAt)}</small>
              </li>
            ))}
          </ul>
        </section>

        <section className="card agent-resizable">
          <div className="card-heading compact"><h2>Agent Activity Log</h2></div>
          <ul className="agent-log">
            {events.length === 0 ? <li>No events</li> : events.map((event) => (
              <li key={event.id} className={`severity-${event.severity}`}>
                <strong>{event.eventType}</strong>
                <span>{event.message}</span>
                <small>{formatDateTime(event.createdAt)}</small>
              </li>
            ))}
          </ul>
        </section>

        <section className="card agent-resizable" data-testid="performance-summary">
          <div className="card-heading compact">
            <div>
              <h2>Performance Summary</h2>
              <p className="agent-subtitle">
                Total P/L is profit or loss (realized + unrealized), not cash moved.
                Invested is open cost basis; taken out is lifetime sell proceeds.
              </p>
            </div>
          </div>
          <div className="metric-grid agent-metrics">
            <div>
              <span>Total P/L (profit)</span>
              <strong className={(performance?.totalPnl || 0) < 0 ? 'negative' : 'positive'}>
                {formatCurrency(performance?.totalPnl)}
              </strong>
            </div>
            <div><span>Realized P/L</span><strong className={(performance?.realizedPnl || 0) < 0 ? 'negative' : 'positive'}>{formatCurrency(performance?.realizedPnl)}</strong></div>
            <div><span>Unrealized P/L</span><strong className={(performance?.unrealizedPnl || 0) < 0 ? 'negative' : 'positive'}>{formatCurrency(performance?.unrealizedPnl)}</strong></div>
            <div>
              <span>Invested now (cost basis)</span>
              <strong>{formatCurrency(performance?.capitalInvested)}</strong>
            </div>
            <div>
              <span>Taken out (sell proceeds)</span>
              <strong>{formatCurrency(performance?.proceedsFromExits)}</strong>
            </div>
            <div>
              <span>Account equity</span>
              <strong>{formatCurrency(performance?.accountEquity)}</strong>
            </div>
            <div><span>Trades</span><strong>{performance?.numberOfTrades ?? 0}</strong></div>
            <div><span>Daily loss hits</span><strong>{performance?.maxDailyLossReachedCount ?? 0}</strong></div>
            <div><span>Blocked by daily loss</span><strong>{performance?.tradesBlockedByDailyLoss ?? 0}</strong></div>
          </div>
        </section>
      </div>
    </div>
  )
}
