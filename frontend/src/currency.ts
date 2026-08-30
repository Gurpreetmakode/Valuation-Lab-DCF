const SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  DKK: 'kr',
  SEK: 'kr',
  NOK: 'kr',
  CHF: 'CHF',
  INR: '₹',
  CNY: '¥',
  HKD: 'HK$',
  CAD: 'C$',
  AUD: 'A$',
};

export function currencySymbol(code: string): string {
  return SYMBOLS[code.toUpperCase()] ?? code.toUpperCase();
}

/** Prefixes a value with its currency symbol, adding a space after
 * multi-character symbols (kr, CHF, HK$) but not single-character ones ($, €). */
export function formatMoney(value: number, symbol: string, decimals = 2): string {
  const separator = symbol.length > 1 ? ' ' : '';
  return `${symbol}${separator}${value.toFixed(decimals)}`;
}
