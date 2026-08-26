import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Account, Position } from './api'
import { PortfolioPanel, type HoldSuggestion } from './PortfolioPanel'

const account: Account = {
  equity: 100_000,
  cash: 25_000,
  buyingPower: 50_000,
}

const positions: Position[] = [
  {
    symbol: 'NVDA',
    quantity: 10,
    marketValue: 1_200,
    averageEntryPrice: 100,
    currentPrice: 120,
    unrealizedPl: 200,
    unrealizedPlPercent: 0.2,
  },
  {
    symbol: 'AAPL',
    quantity: 5,
    marketValue: 900,
    averageEntryPrice: 180,
    currentPrice: 180,
    unrealizedPl: 0,
    unrealizedPlPercent: 0,
  },
]

const suggestions: HoldSuggestion[] = [
  { symbol: 'AAPL', projectedMove: 0.04, holdUntil: '2026-08-25T16:00:00Z' },
  { symbol: 'NVDA', projectedMove: 0.03, holdUntil: '2026-08-25T16:00:00Z' },
]

describe('PortfolioPanel', () => {
  it('renders holdings and selects a symbol', async () => {
    const onSelectSymbol = vi.fn()
    render(
      <PortfolioPanel
        account={account}
        positions={positions}
        state="ready"
        realizedPl={150}
        realizedPlState="ready"
        holdSuggestions={suggestions}
        onSelectSymbol={onSelectSymbol}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Open positions' })).toBeInTheDocument()
    expect(screen.getByText('Equity')).toBeInTheDocument()
    expect(screen.getByText('Open P/L')).toBeInTheDocument()
    expect(screen.getByText('Realized P/L')).toBeInTheDocument()
    const openPl = screen.getByText('Open P/L').parentElement
    expect(openPl?.querySelector('strong')?.textContent).toBe('$200.00')
    const realized = screen.getByText('Realized P/L').parentElement
    expect(realized?.querySelector('strong')?.textContent).toBe('$150.00')
    expect(screen.getByRole('columnheader', { name: '% of equity' })).toBeInTheDocument()
    // NVDA 1200 / 100000 = 1.20%
    expect(screen.getByText('1.20%')).toBeInTheDocument()
    expect(screen.getByText('0.90%')).toBeInTheDocument()
    expect(screen.getByText(/Consider AAPL and NVDA/)).toBeInTheDocument()
    expect(screen.getByText(/Display-only; not advice/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'NVDA' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'NVDA' }))
    expect(onSelectSymbol).toHaveBeenCalledWith('NVDA')
  })

  it('shows an empty state when there are no positions', () => {
    render(
      <PortfolioPanel
        account={account}
        positions={[]}
        state="ready"
        onSelectSymbol={vi.fn()}
      />,
    )
    expect(screen.getByText('No open positions.')).toBeInTheDocument()
    expect(screen.getByText(/Hold ideas appear when the movers scan/)).toBeInTheDocument()
  })
})
