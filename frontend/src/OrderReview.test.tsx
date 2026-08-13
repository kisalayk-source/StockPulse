import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { OrderReview } from './OrderReview'

describe('OrderReview', () => {
  it('shows all material order details before submission', () => {
    render(<OrderReview
      order={{ kind: 'equity', symbol: 'AAPL', side: 'buy', quantity: 3, type: 'limit', limitPrice: 201.25, mode: 'paper' }}
      onCancel={vi.fn()} onConfirm={vi.fn()}
    />)
    expect(screen.getByRole('dialog')).toHaveTextContent('AAPL')
    expect(screen.getByRole('dialog')).toHaveTextContent('BUY')
    expect(screen.getByRole('dialog')).toHaveTextContent('$201.25')
    expect(screen.getByRole('dialog')).toHaveTextContent('paper')
  })

  it('shows pre-trade risk details from the preview', () => {
    render(<OrderReview
      order={{
        kind: 'equity', symbol: 'AAPL', side: 'buy', quantity: 3, type: 'limit',
        limitPrice: 201.25, mode: 'paper',
        preview: { ok: true, estimatedCost: 603.75, positionPct: 0.06, spreadBps: 4.2, dailyPnlPct: 0.01, warnings: ['Prefer a limit'] },
      }}
      onCancel={vi.fn()} onConfirm={vi.fn()}
    />)
    expect(screen.getByRole('dialog')).toHaveTextContent('$603.75')
    expect(screen.getByRole('dialog')).toHaveTextContent('6.0% of equity')
    expect(screen.getByRole('dialog')).toHaveTextContent('Prefer a limit')
  })

  it('cannot submit an order rejected by the risk preview', () => {
    render(<OrderReview
      order={{
        kind: 'equity', symbol: 'AAPL', side: 'buy', quantity: 100, type: 'market',
        mode: 'paper',
        preview: { ok: false, estimatedCost: 20_000, positionPct: 0.5, spreadBps: 5, dailyPnlPct: -0.03, warnings: ['Position limit exceeded'] },
      }}
      onCancel={vi.fn()} onConfirm={vi.fn()}
    />)
    expect(screen.getByRole('button', { name: /submit paper order/i })).toBeDisabled()
  })

  it('makes live risk explicit and requires a deliberate submit click', async () => {
    const onConfirm = vi.fn()
    render(<OrderReview
      order={{ kind: 'option', symbol: 'SPY', contract: 'SPY260821C00600000', side: 'sell', quantity: 1, type: 'market', mode: 'live' }}
      onCancel={vi.fn()} onConfirm={onConfirm}
    />)
    expect(screen.getByText(/LIVE order using real funds/i)).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: /submit live order/i })
    expect(submit).toBeDisabled()
    expect(onConfirm).not.toHaveBeenCalled()
    await userEvent.type(screen.getByLabelText(/authorize this order/i), 'LIVE')
    expect(submit).toBeEnabled()
    await userEvent.click(submit)
    expect(onConfirm).toHaveBeenCalledOnce()
  })
})
