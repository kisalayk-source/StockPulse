import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MarketNewsPanel } from './MarketNewsPanel'

describe('MarketNewsPanel', () => {
  it('renders impact-ranked articles and ticker chips', () => {
    const onSelect = vi.fn()
    render(
      <MarketNewsPanel
        news={[{
          id: '1',
          headline: 'Fed signals rate cut as CPI cools',
          source: 'Reuters',
          url: 'https://example.com/fed',
          publishedAt: '2026-08-12T17:00:00Z',
          sentiment: 'positive',
          impact: 'high',
          impactScore: 8.5,
          symbols: ['SPY'],
        }]}
        loading={false}
        onRefresh={() => undefined}
        onSelectTicker={onSelect}
      />,
    )

    expect(screen.getByText(/HIGH/)).toBeInTheDocument()
    expect(screen.getByText('Fed signals rate cut as CPI cools')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'SPY' }))
    expect(onSelect).toHaveBeenCalledWith('SPY')
  })
})
