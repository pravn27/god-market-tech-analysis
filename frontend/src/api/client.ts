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
  groups: GlobalMarketGroup[]
  breadth: { advancing: number; declining: number; unchanged: number; unavailable: number }
  warnings: string[]
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

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
