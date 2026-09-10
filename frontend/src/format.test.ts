import { describe, expect, it } from 'vitest'
import {
  formatCurrency, formatMarketDateTime, formatNumber, formatPercent,
  localMarketClock, marketStatusLabel, marketStatusTone,
} from './format'

describe('financial formatters', () => {
  it('formats valid values and preserves missing states', () => {
    expect(formatCurrency(1234.5)).toBe('$1,234.50')
    expect(formatCurrency(null)).toBe('—')
    expect(formatNumber(1_250_000, true)).toBe('1.3M')
    expect(formatPercent(2.345)).toBe('2.35%')
    expect(formatPercent(0.0425, false)).toBe('4.25%')
  })
})

describe('market clock', () => {
  it('labels open, extended, and closed sessions', () => {
    expect(marketStatusLabel('regular', true)).toBe('Market Open')
    expect(marketStatusTone('regular', true)).toBe('open')
    expect(marketStatusLabel('pre_market', false)).toBe('Pre-Market')
    expect(marketStatusTone('pre_market', false)).toBe('extended')
    expect(marketStatusLabel('after_hours', false)).toBe('After Hours')
    expect(marketStatusLabel('closed', false)).toBe('Market Closed')
    expect(marketStatusTone('closed', false)).toBe('closed')
  })

  it('classifies US/Eastern weekday and weekend hours', () => {
    expect(localMarketClock(new Date('2026-08-12T14:00:00Z'))).toEqual({
      isOpen: true,
      session: 'regular',
    })
    expect(localMarketClock(new Date('2026-08-12T12:00:00Z'))).toEqual({
      isOpen: false,
      session: 'pre_market',
    })
    expect(localMarketClock(new Date('2026-08-12T21:00:00Z'))).toEqual({
      isOpen: false,
      session: 'after_hours',
    })
    expect(localMarketClock(new Date('2026-08-15T14:00:00Z'))).toEqual({
      isOpen: false,
      session: 'closed',
    })
  })

  it('formats open/close hints in Eastern regardless of host timezone', () => {
    // 13:30 UTC on a summer weekday is 09:30 EDT
    const formatted = formatMarketDateTime('2026-08-13T13:30:00Z')
    expect(formatted).toMatch(/Aug 13/)
    expect(formatted).toMatch(/9:30\s*AM/i)
    expect(formatted).toMatch(/EDT|EST/)
    expect(formatMarketDateTime(null)).toBe('Unavailable')
    expect(formatMarketDateTime('not-a-date')).toBe('Unavailable')
  })
})
