export type MarketDirection = 'advancing' | 'declining' | 'unchanged' | 'unavailable'

export interface GlobalMarketInstrument {
  symbol: string
  display_name: string
  last_price: number | null
  change_percent: number | null
  direction: MarketDirection
  source: 'official_mcp' | 'desktop_bridge' | 'fixture'
  source_timestamp: string | null
  freshness_state: 'ready' | 'unavailable' | 'stale' | 'not_configured'
  warnings: string[]
  unavailable_reason: string | null
}

export interface GlobalMarketGroup {
  name: string
  instruments: GlobalMarketInstrument[]
}

export interface GlobalMarketSnapshot {
  watchlist_name: string
  read_at: string
  timeframe: string
  completeness: 'complete' | 'partial' | 'unavailable'
  desktop_fallback?: 'none' | 'partial' | 'full'
  groups: GlobalMarketGroup[]
  breadth: { advancing: number; declining: number; unchanged: number; unavailable: number }
  warnings: string[]
}

export type AnalysisTimeframe = 'monthly' | 'weekly' | 'daily' | '4h' | '1h' | '15m'
export type Bias = 'bullish' | 'bearish' | 'neutral' | 'unavailable'
export type ScreenSignal = 'BUY' | 'SELL' | 'NOT CLEAR' | 'UNAVAILABLE'
export type FreshnessState = 'ready' | 'unavailable' | 'stale' | 'not_configured'

export interface MtfInstrument {
  symbol: string
  display_name: string
}

export interface MtfInstrumentCatalog {
  watchlist_name: string
  recorded_at: string
  default_symbol: string
  sections: { name: string; instruments: MtfInstrument[] }[]
}

export interface ChecklistCell {
  labels: string[]
  bias: Bias
  values: Record<string, boolean | number | string | null>
  rule_ids: string[]
  unavailable_reason: string | null
}

export interface TimeframeScreen {
  signal: ScreenSignal
  labels: string[]
  unavailable_reason: string | null
}

export interface LayerSignal {
  name: string
  timeframes: AnalysisTimeframe[]
  screen_indicator: string
  signal: ScreenSignal
  screens: Partial<Record<AnalysisTimeframe, TimeframeScreen>>
  missing_timeframes: AnalysisTimeframe[]
}

export interface ScreenDecision {
  name: string
  layers: string[]
  decision: string
  position_note: string | null
  missing_timeframes: AnalysisTimeframe[]
}

export interface MtfTimeframeStatus {
  timeframe: AnalysisTimeframe
  source: GlobalMarketInstrument['source'] | null
  source_timestamp: string | null
  freshness_state: FreshnessState
  live_candle: boolean
  last_close: number | null
  candle_count: number
  unavailable_reason: string | null
}

export interface MtfChecklistRow {
  id: string
  section: string
  label: string
  automated: boolean
  cells: Partial<Record<AnalysisTimeframe, ChecklistCell>>
}

export interface MultiTimeframeAnalysis {
  symbol: string
  display_name: string
  requested_at: string
  profile_version: string
  completeness: 'complete' | 'partial' | 'unavailable'
  timeframes: Partial<Record<AnalysisTimeframe, MtfTimeframeStatus>>
  layers: LayerSignal[]
  rows: MtfChecklistRow[]
  decisions: { double_screens: ScreenDecision[]; triple_screen: ScreenDecision; disclaimer: string }
  warnings: string[]
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json() as { detail?: unknown }
      if (typeof body.detail === 'string') detail = ` ${body.detail}`
    } catch {
      // Non-JSON error bodies only carry the status code.
    }
    throw new Error(`Local API request failed (${response.status}).${detail}`)
  }
  return response.json() as Promise<T>
}

export function getMtfInstruments(signal?: AbortSignal) {
  return getJson<MtfInstrumentCatalog>('/mtf-analysis/instruments', signal)
}

export function getMtfAnalysis(
  symbol: string,
  refreshMode: 'prefer_cache' | 'force_refresh' = 'prefer_cache',
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ refresh_mode: refreshMode })
  return getJson<MultiTimeframeAnalysis>(`/mtf-analysis/${encodeURIComponent(symbol)}?${query}`, signal)
}

export type MtfLiveMessageType = 'snapshot' | 'update' | 'heartbeat' | 'error'

/** One message on the live socket (protocol version 1); `analysis` is set for snapshot and update. */
export interface MtfLiveEnvelope {
  version: number
  type: MtfLiveMessageType
  symbol: string
  sent_at: string
  reason: 'subscribed' | 'candle_close' | 'forming_refresh' | null
  closed_timeframes: AnalysisTimeframe[]
  analysis: MultiTimeframeAnalysis | null
  error: string | null
}

/** WebSocket URL for the live checklist feed, derived from the same base as the HTTP calls. */
export function mtfLiveUrl(symbol: string): string {
  const url = new URL(apiBaseUrl, window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = `${url.pathname.replace(/\/$/, '')}/mtf-analysis/${encodeURIComponent(symbol)}/live`
  url.search = ''
  return url.toString()
}

export async function getGlobalMarketSentiment(
  timeframe = 'daily',
  signal?: AbortSignal,
): Promise<GlobalMarketSnapshot> {
  const response = await fetch(
    `${apiBaseUrl}/global-market-sentiment?${new URLSearchParams({ timeframe })}`,
    { signal, headers: { Accept: 'application/json' } },
  )
  if (!response.ok) {
    throw new Error(`Local market context request failed (${response.status}).`)
  }
  return response.json() as Promise<GlobalMarketSnapshot>
}
