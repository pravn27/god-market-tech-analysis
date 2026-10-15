import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { MultiTimeframeAnalysis } from '../../api/client'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { useMtfLive } from './useMtfLive'

const SYMBOL = 'PEPPERSTONE:NATGAS'
const analysis = { symbol: SYMBOL, display_name: 'NATGAS', completeness: 'complete', rows: [] } as unknown as MultiTimeframeAnalysis

function Probe({ symbol }: { symbol: string | null }) {
  const live = useMtfLive(symbol)
  return <output aria-label="status">{live.status}</output>
}

function renderProbe(queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <Probe symbol={SYMBOL} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  FakeWebSocket.reset()
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

test('connects to the symbol live feed and writes each update into the analysis cache', () => {
  const queryClient = new QueryClient()
  renderProbe(queryClient)

  const socket = FakeWebSocket.instances[0]
  expect(socket.url).toMatch(/\/api\/v1\/mtf-analysis\/PEPPERSTONE%3ANATGAS\/live$/)
  expect(screen.getByLabelText('status')).toHaveTextContent('connecting')

  act(() => socket.open())
  expect(screen.getByLabelText('status')).toHaveTextContent('live')

  act(() => socket.receive({
    version: 1, type: 'update', symbol: SYMBOL, sent_at: '2026-10-15T10:00:00Z',
    reason: 'candle_close', closed_timeframes: ['1h'], analysis, error: null,
  }))
  expect(queryClient.getQueryData(['mtf-analysis', SYMBOL])).toEqual(analysis)
})

test('a dropped socket reconnects after a backoff and reports reconnecting until it reopens', () => {
  vi.useFakeTimers()
  const queryClient = new QueryClient()
  renderProbe(queryClient)
  act(() => FakeWebSocket.instances[0].open())

  act(() => FakeWebSocket.instances[0].drop())
  expect(screen.getByLabelText('status')).toHaveTextContent('reconnecting')
  expect(FakeWebSocket.instances).toHaveLength(1)

  act(() => vi.advanceTimersByTime(2000))
  expect(FakeWebSocket.instances).toHaveLength(2)
  act(() => FakeWebSocket.instances[1].open())
  expect(screen.getByLabelText('status')).toHaveTextContent('live')
})

test('heartbeats keep the feed live without touching the analysis cache', () => {
  const queryClient = new QueryClient()
  renderProbe(queryClient)
  act(() => FakeWebSocket.instances[0].open())

  act(() => FakeWebSocket.instances[0].receive({
    version: 1, type: 'heartbeat', symbol: SYMBOL, sent_at: '2026-10-15T10:00:30Z',
    reason: null, closed_timeframes: [], analysis: null, error: null,
  }))
  expect(screen.getByLabelText('status')).toHaveTextContent('live')
  expect(queryClient.getQueryData(['mtf-analysis', SYMBOL])).toBeUndefined()
})
