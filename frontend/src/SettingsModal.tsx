import { useState, type FormEvent } from 'react'
import { LoaderCircle, X } from 'lucide-react'
import { ApiError, api, type AuthUser, type TradingMode } from './api'

export function SettingsModal({
  user,
  liveTradingEnabled,
  onClose,
  onUpdated,
}: {
  user: AuthUser
  liveTradingEnabled: boolean
  onClose: () => void
  onUpdated: (user: AuthUser) => void
}) {
  const [mode, setMode] = useState<TradingMode>('paper')
  const [keyId, setKeyId] = useState('')
  const [secret, setSecret] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const status = user.alpaca[mode]

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const updated = await api.saveAlpacaCredentials(mode, keyId.trim(), secret.trim())
      onUpdated(updated)
      setKeyId('')
      setSecret('')
      setNotice(`${mode} credentials saved`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save credentials')
    } finally {
      setBusy(false)
    }
  }

  async function clearCredentials() {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const updated = await api.deleteAlpacaCredentials(mode)
      onUpdated(updated)
      setNotice(`${mode} credentials removed`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to remove credentials')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <h2 id="settings-title">Account settings</h2>
            <p>{user.email}</p>
          </div>
          <button type="button" className="icon-button" aria-label="Close settings" onClick={onClose}>
            <X size={18} />
          </button>
        </header>

        <section>
          <h3>Alpaca API keys</h3>
          <p className="settings-copy">
            Trading uses your own Alpaca key and secret. Market data still uses the shared server feed.
          </p>
          <div className="mode-switch settings-mode" aria-label="Credential mode">
            <button type="button" aria-pressed={mode === 'paper'} className={mode === 'paper' ? 'active' : ''} onClick={() => setMode('paper')}>
              Paper
            </button>
            <button
              type="button"
              aria-pressed={mode === 'live'}
              className={mode === 'live' ? 'active live' : ''}
              disabled={!liveTradingEnabled}
              title={!liveTradingEnabled ? 'Live trading is disabled by the server' : undefined}
              onClick={() => setMode('live')}
            >
              Live
            </button>
          </div>
          <p className={`settings-status ${status.configured ? 'ok' : ''}`}>
            {status.configured
              ? `Connected · ${status.keyPreview}`
              : `No ${mode} credentials saved`}
          </p>
          <form className="auth-form" onSubmit={(event) => void save(event)}>
            <label>
              API Key ID
              <input
                value={keyId}
                onChange={(event) => setKeyId(event.target.value)}
                autoComplete="off"
                required
                minLength={8}
                placeholder="PK…"
              />
            </label>
            <label>
              Secret Key
              <input
                type="password"
                value={secret}
                onChange={(event) => setSecret(event.target.value)}
                autoComplete="off"
                required
                minLength={8}
                placeholder="••••••••"
              />
            </label>
            {error && <p className="auth-error" role="alert">{error}</p>}
            {notice && <p className="settings-notice" role="status">{notice}</p>}
            <div className="settings-actions">
              <button type="submit" disabled={busy}>
                {busy ? <LoaderCircle className="spin" size={16} /> : null}
                Save {mode} keys
              </button>
              {status.configured && (
                <button type="button" className="ghost" disabled={busy} onClick={() => void clearCredentials()}>
                  Remove
                </button>
              )}
            </div>
          </form>
        </section>
      </div>
    </div>
  )
}
