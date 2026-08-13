import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import type { OptionPositionIntent, OrderPreview, OrderSide, OrderType, TradingMode } from './api'
import { formatCurrency } from './format'

export interface ReviewOrder {
  kind: 'equity' | 'option'
  symbol: string
  contract?: string
  side: OrderSide
  quantity?: number
  notional?: number
  type: OrderType
  limitPrice?: number
  mode: TradingMode
  positionIntent?: OptionPositionIntent
  preview?: OrderPreview
}

interface OrderReviewProps {
  order: ReviewOrder
  busy?: boolean
  error?: string | null
  onCancel: () => void
  onConfirm: () => void
}

export function OrderReview({ order, busy, error, onCancel, onConfirm }: OrderReviewProps) {
  const [livePhrase, setLivePhrase] = useState('')
  const dialogRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    const dialog = dialogRef.current
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), select:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
    ) || [])
    focusable()[0]?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel()
      if (event.key !== 'Tab') return
      const items = focusable()
      if (!items.length) return
      const first = items[0]
      const last = items.at(-1)
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previouslyFocused?.focus()
    }
  }, [busy, onCancel])

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel()
      }}
    >
      <section ref={dialogRef} className="modal" role="dialog" aria-modal="true" aria-labelledby="review-title" aria-describedby="review-description">
        <button className="icon-button modal-close" onClick={onCancel} aria-label="Close order review">
          <X size={18} />
        </button>
        <span className="eyebrow">Final review</span>
        <h2 id="review-title">Confirm {order.side} order</h2>
        {order.mode === 'live' && (
          <div className="danger-callout">
            <AlertTriangle size={18} />
            This is a LIVE order using real funds.
          </div>
        )}
        <dl className="review-grid">
          <div><dt>Instrument</dt><dd>{order.contract || order.symbol}</dd></div>
          <div><dt>Side</dt><dd className={order.side === 'buy' ? 'positive' : 'negative'}>{order.side.toUpperCase()}</dd></div>
          <div><dt>Quantity</dt><dd>{order.quantity ?? '—'}</dd></div>
          <div><dt>Notional</dt><dd>{formatCurrency(order.notional)}</dd></div>
          <div><dt>Order type</dt><dd>{order.type.toUpperCase()}</dd></div>
          <div><dt>Limit price</dt><dd>{order.type === 'limit' ? formatCurrency(order.limitPrice) : 'Market price'}</dd></div>
          <div><dt>Mode</dt><dd><span className={`mode-badge ${order.mode}`}>{order.mode}</span></dd></div>
          {order.positionIntent && (
            <div><dt>Position intent</dt><dd>{order.positionIntent.replaceAll('_', ' ').toUpperCase()}</dd></div>
          )}
          {order.preview?.estimatedCost != null && (
            <div><dt>Est. cost</dt><dd>{formatCurrency(order.preview.estimatedCost)}</dd></div>
          )}
          {order.preview?.positionPct != null && (
            <div><dt>Position</dt><dd>{(order.preview.positionPct * 100).toFixed(1)}% of equity</dd></div>
          )}
          {order.preview?.spreadBps != null && (
            <div><dt>Spread</dt><dd>{order.preview.spreadBps.toFixed(1)} bps</dd></div>
          )}
        </dl>
        {order.preview?.warnings?.length ? (
          <p className="fine-print">{order.preview.warnings.join(' ')}</p>
        ) : null}
        <p className="fine-print" id="review-description">
          Orders may execute immediately and cannot always be canceled. Kronos forecasts are never
          submitted automatically.
        </p>
        {order.mode === 'live' && (
          <label className="live-order-confirm">
            Type <strong>LIVE</strong> to authorize this order
            <input
              aria-label="Type LIVE to authorize this order"
              value={livePhrase}
              onChange={(event) => setLivePhrase(event.target.value)}
              autoComplete="off"
            />
          </label>
        )}
        {error && <div className="inline-error">{error}</div>}
        <div className="modal-actions">
          <button className="button secondary" onClick={onCancel} disabled={busy}>Go back</button>
          <button className={order.mode === 'live' ? 'button danger' : 'button primary'} onClick={onConfirm} disabled={busy || order.preview?.ok === false || (order.mode === 'live' && livePhrase !== 'LIVE')}>
            {busy ? 'Submitting…' : `Submit ${order.mode} order`}
          </button>
        </div>
      </section>
    </div>
  )
}
