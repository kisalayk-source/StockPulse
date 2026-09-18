import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { GovernmentPanel } from './GovernmentPanel'

describe('GovernmentPanel', () => {
  it('renders government score and activity', () => {
    render(
      <GovernmentPanel
        loading={false}
        data={{
          ticker: 'LMT',
          as_of: '2024-06-01T00:00:00Z',
          government: {
            score: 84,
            early_signal_score: 70,
            awards_30d: 3,
            award_value_30d: 420_000_000,
            obligations_30d: 2,
            obligation_value_30d: 85_000_000,
            opportunity_count_30d: 1,
            opportunity_value_30d: 50_000_000,
            new_customer: true,
            sole_source: true,
            incumbent: true,
            multi_year: false,
            revenue_exposure: 0.12,
            contract_value: 420_000_000,
          },
          recent_activity: [
            {
              date: '2024-05-20',
              agency: 'DoD',
              event: 'AWARD',
              title: 'Missile support',
              value: 420_000_000,
              status: 'AWARD',
            },
          ],
          open_opportunities: [],
          recent_awards: [],
          recent_obligations: [],
          top_agencies: [{ agency: 'DoD', value: 420_000_000 }],
          alerts: [{ type: 'government_score', severity: 'info', message: 'LMT Government Score 84/100' }],
          provider_errors: [],
        }}
      />,
    )
    expect(screen.getByRole('heading', { name: /LMT government activity/i })).toBeInTheDocument()
    expect(screen.getByText('/ 100')).toBeInTheDocument()
    expect(screen.getAllByText(/DoD/).length).toBeGreaterThan(0)
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()
  })
})
