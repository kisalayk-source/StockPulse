import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SecIntelligencePanel } from './SecIntelligencePanel'

describe('SecIntelligencePanel', () => {
  it('renders disclaimer', () => {
    render(
      <SecIntelligencePanel
        loading={false}
        data={{
          ticker: 'XOM',
          caveats: ['13F: Quarterly reported holdings'],
          institutional_changes: [],
          insider_transactions: [],
          major_holder_changes: [],
          accumulation: {
            ticker: 'XOM',
            score: 84,
            signal: 'ACCUMULATION',
            classification: 'STRONG_ACCUMULATION',
            components: { institutional: 88, insider: 76 },
            events: [],
            history: [],
            as_of: '2024-05-01T00:00:00Z',
          },
        }}
      />,
    )
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()
  })
})
