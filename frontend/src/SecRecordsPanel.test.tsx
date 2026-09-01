import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SecRecordsPanel } from './SecIntelligencePanel'

const mockFilingsData = {
  ticker: 'AAPL',
  months: 6,
  cutoff_date: '2024-01-01',
  summary: { '13F': 1, '13D': 0, '13G': 0, '4': 2 },
  filings: [{
    accession_number: '0001',
    form_type: '4',
    form_family: '4',
    filing_date: '2024-03-01',
    report_period: null,
    description: '4',
    is_amendment: false,
    edgar_url: 'https://www.sec.gov/example',
    filer_name: 'Jane Smith',
    action: 'Bought 10,000 shares',
    action_tone: 'positive' as const,
  }],
  insider_transactions: [],
  beneficial_ownership: [],
}

const mockAnalysis = {
  ticker: 'AAPL',
  months: 6,
  headline: 'Recent SEC activity for AAPL looks mostly positive.',
  gist: ['2 Form 4 filings in the last 6 months.', 'Insider activity skews positive.'],
  sentiment: 'good' as const,
  sentiment_label: 'Good news',
  highlights: [{ category: 'insider', text: '1 insider buy', tone: 'positive' as const }],
  source: 'rules' as const,
  disclaimer: 'Not investment advice.',
}

describe('SecRecordsPanel', () => {
  it('renders filings and calls onSearch', async () => {
    const onSearch = vi.fn()
    render(
      <SecRecordsPanel
        symbol="AAPL"
        loading={false}
        onSearch={onSearch}
        data={mockFilingsData}
      />,
    )
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('Form 4')).toBeInTheDocument()
    expect(screen.getByText('Jane Smith')).toBeInTheDocument()
    expect(screen.getByText('Bought 10,000 shares')).toBeInTheDocument()
    await userEvent.clear(screen.getByPlaceholderText(/Search ticker/i))
    await userEvent.type(screen.getByPlaceholderText(/Search ticker/i), 'MSFT')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(onSearch).toHaveBeenCalledWith('MSFT')
  })

  it('renders analysis headline and sentiment badge', () => {
    render(
      <SecRecordsPanel
        symbol="AAPL"
        loading={false}
        onSearch={vi.fn()}
        data={mockFilingsData}
        analysis={mockAnalysis}
      />,
    )
    expect(screen.getByText(mockAnalysis.headline)).toBeInTheDocument()
    expect(screen.getByText('Good news')).toBeInTheDocument()
    expect(screen.getByText(mockAnalysis.gist[0])).toBeInTheDocument()
    expect(screen.getByText(mockAnalysis.gist[1])).toBeInTheDocument()
  })

  it('shows analyzing state while analysis loads', () => {
    render(
      <SecRecordsPanel
        symbol="AAPL"
        loading={false}
        analysisLoading
        onSearch={vi.fn()}
        data={mockFilingsData}
      />,
    )
    expect(screen.getByText(/Analyzing filings/i)).toBeInTheDocument()
  })
})
