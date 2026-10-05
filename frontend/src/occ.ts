/** OCC option: ROOT + YYMMDD + C/P + 8-digit strike. */
const OCC_OPTION_SYMBOL = /^([A-Z]{1,6})(\d{6})[CP]\d{8}$/

/** Parse OCC expiration to ISO date `YYYY-MM-DD`, or null for non-option symbols. */
export function optionExpirationFromSymbol(symbol: string | null | undefined): string | null {
  const match = OCC_OPTION_SYMBOL.exec(String(symbol || '').toUpperCase())
  if (!match) return null
  const yymmdd = match[2]
  const year = 2000 + Number(yymmdd.slice(0, 2))
  const month = Number(yymmdd.slice(2, 4))
  const day = Number(yymmdd.slice(4, 6))
  if (!Number.isFinite(year) || month < 1 || month > 12 || day < 1 || day > 31) return null
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) {
    return null
  }
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}
