import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  OctagonX,
  Pause,
  Play,
  RefreshCw,
  ShieldAlert,
  Square,
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
  type RiskProfile,
  type TradeCandidateRow,
  type TradingAgentConfig,
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
  const [maxLossAmount, setMaxLossAmount] = useState('')
  const [maxLossPercent, setMaxLossPercent] = useState('')

  const applyConfig = useCallback((next: TradingAgentConfig) => {
    setConfig(next)
    setCapital(String(next.capitalAllocation || ''))
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
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load trading agent')
    }
  }, [applyConfig])

  useEffect(() => {
    void refresh()
  }, [refresh])

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

  const daily: DailyLossState | undefined = config?.dailyLoss
  const running = config?.status === 'paper' || config?.status === 'live'

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
        <section className="card">
          <div className="card-heading compact"><h2>Forecast &amp; Opportunity Queue</h2></div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Strategy</th>
                  <th>Signal</th>
                  <th>Confidence</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {candidates.length === 0 ? (
                  <tr><td colSpan={5}>No candidates yet. Start the agent and run a cycle.</td></tr>
                ) : candidates.slice(0, 12).map((row) => (
                  <tr key={row.id}>
                    <td>{row.symbol}</td>
                    <td>{row.strategy}</td>
                    <td>{String(row.forecastSnapshot.signal || '—')}</td>
                    <td>{formatPercent(Number(row.forecastSnapshot.confidence) || null)}</td>
                    <td><span className={`status ${row.status}`}>{row.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="card-heading compact"><h2>Active Positions</h2></div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Entry</th>
                  <th>Mark</th>
                  <th>Unrealized</th>
                </tr>
              </thead>
              <tbody>
                {positions.length === 0 ? (
                  <tr><td colSpan={5}>No open agent positions</td></tr>
                ) : positions.map((row) => (
                  <tr key={row.id}>
                    <td>{row.symbol}</td>
                    <td>{row.quantity}</td>
                    <td>{formatCurrency(row.averageEntryPrice)}</td>
                    <td>{formatCurrency(row.currentPrice)}</td>
                    <td className={row.unrealizedPnl < 0 ? 'negative' : 'positive'}>{formatCurrency(row.unrealizedPnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="card-heading compact"><h2>Trade History</h2></div>
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
                ) : orders.slice(0, 12).map((row) => (
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

        <section className="card">
          <div className="card-heading compact"><h2>Agent Activity Log</h2></div>
          <ul className="agent-log">
            {events.length === 0 ? <li>No events</li> : events.slice(0, 20).map((event) => (
              <li key={event.id} className={`severity-${event.severity}`}>
                <strong>{event.eventType}</strong>
                <span>{event.message}</span>
                <small>{formatDateTime(event.createdAt)}</small>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <div className="card-heading compact"><h2>Performance Summary</h2></div>
          <div className="metric-grid agent-metrics">
            <div><span>Total P/L</span><strong className={(performance?.totalPnl || 0) < 0 ? 'negative' : 'positive'}>{formatCurrency(performance?.totalPnl)}</strong></div>
            <div><span>Realized</span><strong>{formatCurrency(performance?.realizedPnl)}</strong></div>
            <div><span>Unrealized</span><strong>{formatCurrency(performance?.unrealizedPnl)}</strong></div>
            <div><span>Trades</span><strong>{performance?.numberOfTrades ?? 0}</strong></div>
            <div><span>Daily loss hits</span><strong>{performance?.maxDailyLossReachedCount ?? 0}</strong></div>
            <div><span>Blocked by daily loss</span><strong>{performance?.tradesBlockedByDailyLoss ?? 0}</strong></div>
          </div>
        </section>
      </div>
    </div>
  )
}
