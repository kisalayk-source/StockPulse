import { describe, expect, it } from 'vitest'
import { optionExpirationFromSymbol } from './occ'

describe('optionExpirationFromSymbol', () => {
  it('parses OCC YYMMDD into ISO date', () => {
    expect(optionExpirationFromSymbol('AAPL260821C00200000')).toBe('2026-08-21')
    expect(optionExpirationFromSymbol('spy260117p00450000')).toBe('2026-01-17')
  })

  it('returns null for equities and invalid contracts', () => {
    expect(optionExpirationFromSymbol('NVDA')).toBeNull()
    expect(optionExpirationFromSymbol('')).toBeNull()
    expect(optionExpirationFromSymbol('AAPL991332C00200000')).toBeNull()
  })
})
