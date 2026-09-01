import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SecRecordsPanel } from './SecIntelligencePanel'

describe('SecRecordsPanel', () => {
  it('renders filings and calls onSearch', async () => {
    const onSearch = vi.fn()
    render(
      <SecRecordsPanel
        symbol="AAPL"
        loading={false}
        onSearch={onSearch}
        data={{
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
          }],
          insider_transactions: [],
          beneficial_ownership: [],
        }}
      />,
    )
    expect(screen.getByText(/Form 4: 2/)).toBeInTheDocument()
    await userEvent.clear(screen.getByPlaceholderText(/Search ticker/i))
    await userEvent.type(screen.getByPlaceholderText(/Search ticker/i), 'MSFT')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(onSearch).toHaveBeenCalledWith('MSFT')
  })
})
