import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import {
  globalMarketLiveUrl,
  type GlobalMarketLiveEnvelope,
  type GlobalMarketTimeframe,
} from '../../api/client'

export type GlobalMarketLiveStatus = 'connecting' | 'live' | 'reconnecting' | 'paused'

/**
 * Live WebSocket updates. The server must also opt in (GLOBAL_MARKET_LIVE_ENABLED=true); when it
 * does not, the socket is rejected with 1008 and the badge shows PAUSED. Refreshes run every five
 * minutes on the server, because each refresh calls the TradingView MCP once per instrument.
 */
export const GLOBAL_MARKET_LIVE_ENABLED = true

export interface GlobalMarketLiveState {
  status: GlobalMarketLiveStatus
  lastUpdate: Date | null
  error: string | null
}

const MAX_BACKOFF_MS = 30_000
const POLICY_VIOLATION_CLOSE = 1008
// The server sends a heartbeat every 30 seconds; three missed heartbeats mean the socket is dead.
const SILENCE_LIMIT_MS = 90_000

export const initialLiveState: GlobalMarketLiveState = { status: 'connecting', lastUpdate: null, error: null }
export const pausedLiveState: GlobalMarketLiveState = { status: 'paused', lastUpdate: null, error: null }

/**
 * Opens one reconnecting socket for a timeframe. Each snapshot is written into the same query cache
 * entry that `useGlobalMarket` reads, so the page updates without a refetch. Returns a stop function.
 */
function connectGlobalMarketFeed(
  queryClient: QueryClient,
  timeframe: GlobalMarketTimeframe,
  report: (patch: Partial<GlobalMarketLiveState>) => void,
): () => void {
  let socket: WebSocket | null = null
  let retryTimer: ReturnType<typeof setTimeout> | undefined
  let silenceTimer: ReturnType<typeof setTimeout> | undefined
  let attempt = 0
  let stopped = false

  const armSilenceWatch = () => {
    clearTimeout(silenceTimer)
    silenceTimer = setTimeout(() => socket?.close(), SILENCE_LIMIT_MS)
  }

  const connect = () => {
    report({ status: attempt === 0 ? 'connecting' : 'reconnecting' })
    const current = new WebSocket(globalMarketLiveUrl(timeframe))
    socket = current
    current.onopen = () => {
      attempt = 0
      report({ status: 'live' })
      armSilenceWatch()
    }
    current.onmessage = (event: MessageEvent<string>) => {
      armSilenceWatch()
      const envelope = JSON.parse(event.data) as GlobalMarketLiveEnvelope
      if (envelope.type === 'error') {
        report({ error: envelope.error })
        return
      }
      if (envelope.snapshot) {
        queryClient.setQueryData(['global-market-sentiment', timeframe], envelope.snapshot)
        report({ lastUpdate: new Date(envelope.sent_at), error: null })
      }
    }
    current.onclose = (event: CloseEvent) => {
      clearTimeout(silenceTimer)
      if (stopped) return
      // 1008 means the server has live updates switched off; retrying cannot succeed, so stop here.
      if (event.code === POLICY_VIOLATION_CLOSE) {
        report({ status: 'paused' })
        return
      }
      attempt += 1
      report({ status: 'reconnecting' })
      retryTimer = setTimeout(connect, Math.min(MAX_BACKOFF_MS, 1000 * 2 ** attempt))
    }
  }

  connect()
  return () => {
    stopped = true
    clearTimeout(retryTimer)
    clearTimeout(silenceTimer)
    socket?.close()
  }
}

/**
 * Keeps the given timeframes live over the backend WebSocket, one socket per timeframe.
 * Returns each timeframe's live state keyed by timeframe value.
 */
export function useGlobalMarketLive(timeframes: GlobalMarketTimeframe[], enabled = true) {
  const queryClient = useQueryClient()
  const [states, setStates] = useState<Partial<Record<GlobalMarketTimeframe, GlobalMarketLiveState>>>({})
  const key = timeframes.join(',')

  useEffect(() => {
    if (!enabled) return undefined
    const active = key === '' ? [] : (key.split(',') as GlobalMarketTimeframe[])
    const stops = active.map((timeframe) =>
      connectGlobalMarketFeed(queryClient, timeframe, (patch) =>
        setStates((previous) => ({
          ...previous,
          [timeframe]: { ...(previous[timeframe] ?? initialLiveState), ...patch },
        })),
      ),
    )
    return () => stops.forEach((stop) => stop())
  }, [enabled, key, queryClient])

  return states
}
