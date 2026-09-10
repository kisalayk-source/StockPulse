import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { ApiError, api, type RiskManagementConfig, type RiskProfile } from './api'

const CUSTOM_FIELDS: Array<{ key: string; label: string; type?: 'number' | 'checkbox' | 'text' }> = [
  { key: 'starting_capital', label: 'Starting capital' },
  { key: 'max_portfolio_exposure', label: 'Max portfolio exposure (0-1)' },
  { key: 'max_position_size_pct', label: 'Max position size % (0-1)' },
  { key: 'max_risk_per_trade_pct', label: 'Max risk per trade % (0-1)' },
  { key: 'max_daily_loss_amount', label: 'Max daily loss $' },
  { key: 'max_daily_loss_percent', label: 'Max daily loss %' },
  { key: 'max_portfolio_drawdown', label: 'Max portfolio drawdown (0-1)' },
  { key: 'max_open_positions', label: 'Max open positions' },
  { key: 'max_weekly_loss_percent', label: 'Max weekly loss %' },
  { key: 'max_monthly_loss_percent', label: 'Max monthly loss %' },
  { key: 'allow_options', label: 'Allow options', type: 'checkbox' },
  { key: 'allow_naked_options', label: 'Allow naked options', type: 'checkbox' },
  { key: 'allow_day_trading', label: 'Allow day trading', type: 'checkbox' },
  { key: 'short_selling_enabled', label: 'Short selling', type: 'checkbox' },
  { key: 'min_forecast_confidence', label: 'Min forecast confidence' },
  { key: 'max_order_value', label: 'Max order value' },
  { key: 'daily_loss_timezone', label: 'Daily loss timezone', type: 'text' },
  { key: 'daily_loss_reset_time', label: 'Daily loss reset time', type: 'text' },
  { key: 'daily_loss_action', label: 'Daily loss action', type: 'text' },
  { key: 'daily_loss_calculation', label: 'Daily loss calculation', type: 'text' },
]

export function RiskManagementPanel({ onClose }: { onClose?: () => void }) {
  const [config, setConfig] = useState<RiskManagementConfig | null>(null)
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [profile, setProfile] = useState<RiskProfile>('medium')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const payload = await api.getRiskManagementConfig()
        setConfig(payload)
        setProfile(payload.riskProfile)
        setDraft({ ...payload.riskConfig })
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Unable to load risk settings')
      }
    })()
  }, [])

  async function save() {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const updated = await api.updateRiskManagementConfig({
        risk_profile: profile,
        risk_config: profile === 'custom' ? draft : undefined,
      })
      setConfig(updated)
      setDraft({ ...updated.riskConfig })
      setNotice('Risk settings saved')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save risk settings')
    } finally {
      setBusy(false)
    }
  }

  async function resetDefaults() {
    setBusy(true)
    setError('')
    try {
      const updated = await api.resetRiskManagementConfig()
      setConfig(updated)
      setProfile(updated.riskProfile)
      setDraft({ ...updated.riskConfig })
      setNotice('Profile defaults restored (daily loss state preserved)')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to reset risk settings')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="risk-management-page" data-testid="risk-management-page">
      <section className="card">
        <div className="card-heading">
          <div>
            <p className="label">/settings/risk-management</p>
            <h2>Risk management</h2>
            <p className="agent-subtitle">Low / Medium / High presets with full custom controls</p>
          </div>
          {onClose ? (
            <button type="button" className="icon-button" aria-label="Close risk settings" onClick={onClose}>
              <X size={18} />
            </button>
          ) : null}
        </div>

        {error && <p className="settings-error">{error}</p>}
        {notice && <p className="settings-notice">{notice}</p>}

        <label>
          <span>Risk profile</span>
          <select
            value={profile}
            disabled={busy}
            onChange={(event) => setProfile(event.target.value as RiskProfile)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="custom">Custom</option>
          </select>
        </label>

        <div className="risk-fields">
          {CUSTOM_FIELDS.map((field) => {
            const value = draft[field.key]
            if (field.type === 'checkbox') {
              return (
                <label key={field.key} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={Boolean(value)}
                    disabled={busy || profile !== 'custom'}
                    onChange={(event) =>
                      setDraft((prev) => ({ ...prev, [field.key]: event.target.checked }))
                    }
                  />
                  <span>{field.label}</span>
                </label>
              )
            }
            return (
              <label key={field.key}>
                <span>{field.label}</span>
                <input
                  type={field.type === 'text' ? 'text' : 'number'}
                  value={value == null ? '' : String(value)}
                  disabled={busy || (profile !== 'custom' && !String(field.key).startsWith('daily_loss') && field.key !== 'max_daily_loss_amount' && field.key !== 'max_daily_loss_percent')}
                  onChange={(event) => {
                    const next =
                      field.type === 'text'
                        ? event.target.value
                        : event.target.value === ''
                          ? null
                          : Number(event.target.value)
                    setDraft((prev) => ({ ...prev, [field.key]: next }))
                  }}
                />
              </label>
            )
          })}
        </div>

        <div className="modal-actions">
          <button type="button" disabled={busy} onClick={() => void resetDefaults()}>
            Reset to profile defaults
          </button>
          <button type="button" className="primary" disabled={busy} onClick={() => void save()}>
            Save risk settings
          </button>
        </div>

        {config?.dailyLoss ? (
          <p className="agent-subtitle">
            Daily loss status: {config.dailyLoss.status} · remaining{' '}
            {config.dailyLoss.remainingDailyLoss ?? '—'}
          </p>
        ) : null}
      </section>
    </div>
  )
}
