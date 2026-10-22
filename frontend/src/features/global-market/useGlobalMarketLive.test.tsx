import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { GlobalMarketSnapshot, GlobalMarketTimeframe } from '../../api/client'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { useGlobalMarketLive } from './useGlobalMarketLive'

const snapshot = {
  watchlist_name: 'PS_Global_Indices',
  read_at: '2026-10-22T04:00:00Z',
  timeframe: '1D',
  completeness: 'complete',
  breadth: { advancing: 1, declining: 0, unchanged: 0, unavailable: 0 },
  warnings: [],
  groups: [],
} as unknown as GlobalMarketSnapshot

function Probe({ timeframes }: { timeframes: GlobalMarketTimeframe[] }) {
  const states = useGlobalMarketLive(timeframes)
  return (
    <output aria-label="status">
      {timeframes.map((tf) => `${tf}:${states[tf]?.status ?? 'none'}`).join(' ')}
    </output>
  )
}

function renderProbe(queryClient: QueryClient, timeframes: GlobalMarketTimeframe[]) {
  return render(
    <QueryClientProvider client={queryClient}>
      <Probe timeframes={timeframes} />
    </QueryClientProvider>,
  )
}

const socketFor = (timeframe: string) =>
  FakeWebSocket.instances.find((socket) => socket.url.endsWith(`timeframe=${timeframe}`))!

beforeEach(() => {
  FakeWebSocket.reset()
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

test('opens one socket per timeframe on the live global-market route', () => {
  renderProbe(new QueryClient(), ['1D', '1W'])

  expect(FakeWebSocket.instances).toHaveLength(2)
  expect(socketFor('1D').url).toMatch(/\/api\/v1\/global-market-sentiment\/live\?timeframe=1D$/)
  expect(socketFor('1W').url).toMatch(/\/global-market-sentiment\/live\?timeframe=1W$/)
  expect(screen.getByLabelText('status')).toHaveTextContent('1D:connecting 1W:connecting')
})

test('a snapshot from the socket is written into the timeframe cache entry', () => {
  const queryClient = new QueryClient()
  renderProbe(queryClient, ['1D'])

  act(() => socketFor('1D').open())
  expect(screen.getByLabelText('status')).toHaveTextContent('1D:live')

  act(() => socketFor('1D').receive({
    version: 1, type: 'update', timeframe: '1D', sent_at: '2026-10-22T04:01:00Z', snapshot, error: null,
  }))
  expect(queryClient.getQueryData(['global-market-sentiment', '1D'])).toEqual(snapshot)
})

test('an error envelope keeps the last snapshot and reports the refresh failure', () => {
  const queryClient = new QueryClient()
  queryClient.setQueryData(['global-market-sentiment', '1D'], snapshot)
  renderProbe(queryClient, ['1D'])
  act(() => socketFor('1D').open())

  act(() => socketFor('1D').receive({
    version: 1, type: 'error', timeframe: '1D', sent_at: '2026-10-22T04:01:00Z', snapshot: null,
    error: 'Live refresh failed; retrying shortly.',
  }))
  expect(queryClient.getQueryData(['global-market-sentiment', '1D'])).toEqual(snapshot)
})

test('a dropped socket reconnects after a backoff and reports reconnecting until it reopens', () => {
  vi.useFakeTimers()
  renderProbe(new QueryClient(), ['1D'])
  act(() => socketFor('1D').open())

  act(() => socketFor('1D').drop())
  expect(screen.getByLabelText('status')).toHaveTextContent('1D:reconnecting')
  expect(FakeWebSocket.instances).toHaveLength(1)

  act(() => vi.advanceTimersByTime(2000))
  expect(FakeWebSocket.instances).toHaveLength(2)
  act(() => FakeWebSocket.instances[1].open())
  expect(screen.getByLabelText('status')).toHaveTextContent('1D:live')
})

test('heartbeats keep the feed live without touching the cache', () => {
  const queryClient = new QueryClient()
  renderProbe(queryClient, ['1D'])
  act(() => socketFor('1D').open())

  act(() => socketFor('1D').receive({
    version: 1, type: 'heartbeat', timeframe: '1D', sent_at: '2026-10-22T04:00:30Z', snapshot: null, error: null,
  }))
  expect(screen.getByLabelText('status')).toHaveTextContent('1D:live')
  expect(queryClient.getQueryData(['global-market-sentiment', '1D'])).toBeUndefined()
})

test('unmounting closes the timeframe sockets and stops reconnecting', () => {
  vi.useFakeTimers()
  const { unmount } = renderProbe(new QueryClient(), ['1D'])
  act(() => socketFor('1D').open())
  act(() => socketFor('1D').drop())

  unmount()
  act(() => vi.advanceTimersByTime(60_000))
  expect(FakeWebSocket.instances).toHaveLength(1)
})

test('a 1008 close from the server stops reconnecting and reports paused', () => {
  vi.useFakeTimers()
  renderProbe(new QueryClient(), ['1D'])
  act(() => socketFor('1D').open())

  act(() => socketFor('1D').dropWithCode(1008))
  act(() => vi.advanceTimersByTime(60_000))

  expect(screen.getByLabelText('status')).toHaveTextContent('1D:paused')
  expect(FakeWebSocket.instances).toHaveLength(1)
})
