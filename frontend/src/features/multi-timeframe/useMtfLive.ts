import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { mtfLiveUrl, type MtfLiveEnvelope } from '../../api/client'

export type LiveStatus = 'connecting' | 'live' | 'reconnecting'

const MAX_BACKOFF_MS = 30_000
// The server sends a heartbeat every 30 seconds; three missed heartbeats mean the socket is dead.
const SILENCE_LIMIT_MS = 90_000

/**
 * Keeps the checklist live over the backend WebSocket. Each analysis update is written into the
 * same query cache entry that `useMtfAnalysis` reads, so the page re-renders without a refetch.
 */
export function useMtfLive(symbol: string | null) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<LiveStatus>('connecting')
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [liveError, setLiveError] = useState<string | null>(null)

  useEffect(() => {
    if (symbol === null) return undefined

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
      setStatus(attempt === 0 ? 'connecting' : 'reconnecting')
      const current = new WebSocket(mtfLiveUrl(symbol))
      socket = current
      current.onopen = () => {
        attempt = 0
        setStatus('live')
        armSilenceWatch()
      }
      current.onmessage = (event: MessageEvent<string>) => {
        armSilenceWatch()
        const envelope = JSON.parse(event.data) as MtfLiveEnvelope
        if (envelope.type === 'error') {
          setLiveError(envelope.error)
          return
        }
        if (envelope.analysis) {
          queryClient.setQueryData(['mtf-analysis', symbol], envelope.analysis)
          setLastUpdate(new Date(envelope.sent_at))
          setLiveError(null)
        }
      }
      current.onclose = () => {
        clearTimeout(silenceTimer)
        if (stopped) return
        attempt += 1
        setStatus('reconnecting')
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
  }, [symbol, queryClient])

  return { status, lastUpdate, liveError }
}
