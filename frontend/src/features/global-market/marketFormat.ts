import type { GlobalMarketInstrument, GlobalMarketTimeframe } from '../../api/client'
import { marketColors } from '../../theme'

export const NEUTRAL_BAND_PERCENT = 0.5

/** Same 12-hour clock with AM/PM as the multi-timeframe page: "Oct 22, 2026, 7:41 PM". */
export function formatMarketDateTime(value: string | Date) {
  return new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short', hour12: true }).format(new Date(value))
}

/** Time only, 12-hour with AM/PM, for the live "Updated" stamp: "7:41:05 PM". */
export function formatMarketTime(value: Date) {
  return new Intl.DateTimeFormat('en-US', { timeStyle: 'medium', hour12: true }).format(value)
}

export type SentimentLabel = 'Bullish' | 'Neutral' | 'Bearish'

export interface SentimentBreakdown {
  bullish: number
  neutral: number
  bearish: number
  unavailable: number
  total: number
  dominantLabel: SentimentLabel
  dominantPercent: number
}

export const sourceLabel: Record<GlobalMarketInstrument['source'], string> = {
  official_mcp: 'OFFICIAL MCP',
  desktop_bridge: 'DESKTOP ASSISTED',
  fixture: 'FIXTURE',
}

export const sourceColor: Record<GlobalMarketInstrument['source'], string> = {
  official_mcp: 'blue',
  desktop_bridge: 'gold',
  fixture: 'default',
}

export const freshnessColor: Record<GlobalMarketInstrument['freshness_state'], string> = {
  ready: 'success',
  stale: 'warning',
  unavailable: 'error',
  not_configured: 'default',
}

export const sentimentTagColor: Record<SentimentLabel, string> = {
  Bullish: 'green',
  Neutral: 'default',
  Bearish: 'red',
}

export function formatPrice(value: number | null) {
  return value === null
    ? '—'
    : value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatChange(value: number | null) {
  return value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

export function shortSymbol(symbol: string) {
  return symbol.includes(':') ? symbol.slice(symbol.indexOf(':') + 1) : symbol
}

export function changeColor(value: number | null) {
  if (value === null || value === 0) return marketColors.neutral
  return value > 0 ? marketColors.bullish : marketColors.bearish
}

export function changeTagColor(value: number | null) {
  if (value === null || value === 0) return 'default'
  return value > 0 ? 'green' : 'red'
}

export function calculateSentiment(instruments: GlobalMarketInstrument[]): SentimentBreakdown {
  const counts = { bullish: 0, neutral: 0, bearish: 0, unavailable: 0 }
  for (const { change_percent: change } of instruments) {
    if (change === null) counts.unavailable += 1
    else if (change > NEUTRAL_BAND_PERCENT) counts.bullish += 1
    else if (change < -NEUTRAL_BAND_PERCENT) counts.bearish += 1
    else counts.neutral += 1
  }
  const total = counts.bullish + counts.neutral + counts.bearish
  const percent = (count: number) => (total > 0 ? Math.round((count / total) * 100) : 0)
  const ranked: [SentimentLabel, number][] = [
    ['Neutral', counts.neutral],
    ['Bullish', counts.bullish],
    ['Bearish', counts.bearish],
  ]
  const [dominantLabel, dominantCount] = ranked.reduce((best, entry) => (entry[1] > best[1] ? entry : best))
  return { ...counts, total, dominantLabel, dominantPercent: percent(dominantCount) }
}

/** Dropdown order matches the Global Market timeframe selector; values are the API's interval codes. */
export const globalMarketTimeframes: { value: GlobalMarketTimeframe; label: string; short: string }[] = [
  { value: '3M', label: '3 Month', short: '3M' },
  { value: 'M', label: 'Monthly', short: 'M' },
  { value: '1W', label: 'Weekly', short: 'W' },
  { value: '1D', label: 'Daily', short: 'D' },
  { value: '4h', label: '4 Hour', short: '4H' },
  { value: '1h', label: '1 Hour', short: '1H' },
]

export function timeframeName(value: string) {
  return globalMarketTimeframes.find((item) => item.value === value)?.label ?? value
}
