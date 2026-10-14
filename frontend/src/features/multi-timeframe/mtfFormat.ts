import type { AnalysisTimeframe, Bias, ScreenSignal } from '../../api/client'

export const timeframeLabel: Record<AnalysisTimeframe, string> = {
  monthly: 'Monthly',
  weekly: 'Weekly',
  daily: 'Daily',
  '4h': '4H',
  '1h': '1H',
  '15m': '15m',
}

export const biasColor: Record<Bias, string> = {
  bullish: 'success',
  bearish: 'error',
  neutral: 'default',
  unavailable: 'warning',
}

// EMA price-relation labels such as "Price > 26" (green) and "Price < 26" (red), other labels keep the cell bias colour.
const emaPriceRelation = /^Price ([<>]) \d+$/

export function labelColor(rowId: string, label: string, bias: Bias): string {
  if (rowId === 'emas') {
    const relation = emaPriceRelation.exec(label)?.[1]
    if (relation === '>') return 'success'
    if (relation === '<') return 'error'
  }
  return biasColor[bias]
}

export const signalColor: Record<ScreenSignal, string> = {
  BUY: 'success',
  SELL: 'error',
  'NOT CLEAR': 'default',
  UNAVAILABLE: 'warning',
}

export function decisionTone(decision: string): 'buy' | 'sell' | 'neutral' | 'incomplete' {
  if (decision.startsWith('INCOMPLETE')) return 'incomplete'
  if (decision.startsWith('BUY')) return 'buy'
  if (decision.startsWith('SELL')) return 'sell'
  return 'neutral'
}

export function formatTimestamp(value: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

export function formatValue(value: boolean | number | string | null) {
  if (value === null) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string') return value
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
}
