import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { FakeWebSocket } from '../../test/fakeWebSocket'
import GlobalMarketPage from './GlobalMarketPage'

const fixtureSnapshot = {
  watchlist_name: 'PS_Global_Indices',
  read_at: '2026-10-06T12:00:00Z',
  timeframe: '1D',
  completeness: 'partial',
  breadth: { advancing: 2, declining: 1, unchanged: 0, unavailable: 1 },
  warnings: ['Fixture data only: values are illustrative.'],
  groups: [
    {
      name: 'USA',
      instruments: [
        {
          symbol: 'TVC:DJI',
          display_name: 'Dow Jones Industrial Average',
          last_price: 100,
          change_percent: 0.45,
          direction: 'advancing',
          source: 'fixture',
          source_timestamp: '2026-10-06T12:00:00Z',
          freshness_state: 'ready',
          warnings: [],
          unavailable_reason: null,
        },
      ],
    },
    {
      name: 'INDIA ADRS',
      instruments: [
        {
          symbol: 'NYSE:INFY',
          display_name: 'Infosys ADR',
          last_price: null,
          change_percent: null,
          direction: 'unavailable',
          source: 'fixture',
          source_timestamp: null,
          freshness_state: 'unavailable',
          warnings: [],
          unavailable_reason: 'Fixture does not include a current value for this item.',
        },
      ],
    },
  ],
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <GlobalMarketPage />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  FakeWebSocket.reset()
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('renders sentiment, ordered groups, fixture warning, and unavailable evidence', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(fixtureSnapshot), { status: 200 })))

  renderPage()

  expect(await screen.findByRole('heading', { name: 'USA' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'INDIA ADRS' })).toBeInTheDocument()
  expect(screen.getByText('Dow Jones Industrial Average')).toBeInTheDocument()
  expect(screen.getByText(/Fixture data only/i)).toBeInTheDocument()

  const sentiment = screen.getByRole('region', { name: 'Market sentiment' })
  expect(within(sentiment).getByText('NEUTRAL')).toBeInTheDocument()
  expect(within(sentiment).getByText(/Based on 1 instruments across 2 sections · 1 unavailable/)).toBeInTheDocument()
  const neutralCard = within(sentiment).getByText('Neutral').closest('.ant-card')
  expect(within(neutralCard as HTMLElement).getByText('100% of markets')).toBeInTheDocument()

  const unavailableCard = screen.getByRole('button', { name: 'View evidence for Infosys ADR' })
  expect(within(unavailableCard).getByText('Unavailable')).toBeInTheDocument()
  expect(within(unavailableCard).getByText('—')).toBeInTheDocument()
})

test('classifies group sentiment with the ±0.5% neutral band', async () => {
  const usa = fixtureSnapshot.groups[0]
  const movingSnapshot = {
    ...fixtureSnapshot,
    groups: [{
      ...usa,
      instruments: [
        { ...usa.instruments[0], symbol: 'TVC:SPX', change_percent: 1.2 },
        { ...usa.instruments[0], symbol: 'TVC:NDX', change_percent: -0.9 },
        { ...usa.instruments[0], symbol: 'TVC:RUT', change_percent: -0.6 },
      ],
    }],
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(movingSnapshot), { status: 200 })))

  renderPage()

  await screen.findByRole('heading', { name: 'USA' })
  expect(screen.getByText('67% Bearish')).toBeInTheDocument()
  expect(within(screen.getByRole('region', { name: 'Market sentiment' })).getByText('BEARISH')).toBeInTheDocument()
})

test('refresh refetches only the local API', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify(fixtureSnapshot), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  renderPage()

  await screen.findByText('Dow Jones Industrial Average')
  fireEvent.click(screen.getByRole('button', { name: /Refresh/ }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/global-market-sentiment?timeframe=1D')
})

test('shows a clear local API error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 503 })))

  renderPage()

  expect(await screen.findByText(/Local market context request failed/i)).toBeInTheDocument()
})

test('shows an empty state when the local API has no groups', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...fixtureSnapshot, groups: [] }), { status: 200 })),
  )

  renderPage()

  expect(await screen.findByText(/No watchlist groups are available/i)).toBeInTheDocument()
})

test('labels Desktop-assisted fallback values in table and card views', async () => {
  const desktopSnapshot = {
    ...fixtureSnapshot,
    groups: fixtureSnapshot.groups.map((group) => ({
      ...group,
      instruments: group.instruments.map((instrument) => ({
        ...instrument,
        source: 'desktop_bridge' as const,
        warnings: ['Desktop-assisted fallback quote.'],
      })),
    })),
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(desktopSnapshot), { status: 200 })))

  renderPage()

  expect(await screen.findAllByText('DESKTOP ASSISTED')).toHaveLength(2)
  expect(screen.queryByText(/Official TradingView MCP is unavailable/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('radio', { name: /Table/ }))
  expect(screen.getAllByText('DESKTOP ASSISTED')).toHaveLength(2)
})

test('shows a banner when Desktop quotes replace or supplement official data', async () => {
  const desktop = (instrument: (typeof fixtureSnapshot.groups)[number]['instruments'][number]) => ({
    ...instrument,
    source: 'desktop_bridge' as const,
  })
  const fullFallback = {
    ...fixtureSnapshot,
    desktop_fallback: 'full',
    groups: fixtureSnapshot.groups.map((group) => ({ ...group, instruments: group.instruments.map(desktop) })),
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(fullFallback), { status: 200 })))

  const { unmount } = renderPage()

  expect(await screen.findByText(/Official TradingView MCP is unavailable/)).toBeInTheDocument()
  unmount()

  const partialFallback = {
    ...fixtureSnapshot,
    desktop_fallback: 'partial',
    groups: [
      { ...fixtureSnapshot.groups[0], instruments: fixtureSnapshot.groups[0].instruments.map(desktop) },
      fixtureSnapshot.groups[1],
    ],
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(partialFallback), { status: 200 })))

  renderPage()

  expect(await screen.findByText('TradingView Desktop watchlist filled 1 item the official MCP could not supply')).toBeInTheDocument()
})

test('opens read-only evidence details from cards and from the table', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(fixtureSnapshot), { status: 200 })))

  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: 'View evidence for Infosys ADR' }))
  expect(await screen.findByText('Market evidence: Infosys ADR')).toBeInTheDocument()
  expect(screen.getByText(/Fixture does not include a current value/i)).toBeInTheDocument()

  fireEvent.click(screen.getByRole('radio', { name: /Table/ }))
  expect(screen.getByRole('table', { name: 'USA market instruments' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'View evidence for Dow Jones Industrial Average' }))
  expect(await screen.findByText('Market evidence: Dow Jones Industrial Average')).toBeInTheDocument()
})

test('defaults to cards, single-timeframe daily analysis, and presents view controls', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(fixtureSnapshot), { status: 200 })))

  renderPage()

  await screen.findByText('Dow Jones Industrial Average')
  expect(screen.getByRole('switch', { name: 'Analysis mode: all timeframes' })).not.toBeChecked()
  expect(screen.getByRole('combobox', { name: 'Timeframe' }).closest('.ant-select')).toHaveTextContent('Daily')
  expect(screen.getByRole('radiogroup', { name: 'Market view' })).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: /Cards/ })).toBeChecked()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})

test('all timeframes mode loads every timeframe and shows one column per timeframe', async () => {
  const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(fixtureSnapshot), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  renderPage()
  await screen.findByText('Dow Jones Industrial Average')
  fireEvent.click(screen.getByRole('switch', { name: 'Analysis mode: all timeframes' }))

  const matrix = await screen.findByRole('table', { name: 'All timeframes market instruments' })
  for (const label of ['3M', 'M', 'W', 'D', '4H', '1H']) {
    expect(within(matrix).getByRole('columnheader', { name: label })).toBeInTheDocument()
  }
  const urls = fetchMock.mock.calls.map(([url]) => url as string)
  for (const tf of ['3M', 'M', '1W', '1D', '4h', '1h']) {
    expect(urls).toContain(`/api/v1/global-market-sentiment?timeframe=${tf}`)
  }
  expect(screen.getByRole('combobox', { name: 'Timeframe' })).toBeDisabled()
  expect(screen.getByRole('radio', { name: /Cards/ })).toBeDisabled()
})

test('the timeframe dropdown lists the six timeframes and requests the chosen one', async () => {
  const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(fixtureSnapshot), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  renderPage()
  await screen.findByText('Dow Jones Industrial Average')
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Timeframe' }))

  for (const label of ['3 Month', 'Monthly', 'Weekly', 'Daily', '4 Hour', '1 Hour']) {
    expect(await screen.findByText(label, { selector: '.ant-select-item-option-content' })).toBeInTheDocument()
  }
  fireEvent.click(screen.getByText('4 Hour', { selector: '.ant-select-item-option-content' }))

  await waitFor(() =>
    expect(fetchMock.mock.calls.map(([url]) => url)).toContain('/api/v1/global-market-sentiment?timeframe=4h'),
  )
})

test('live refresh is paused: the page opens no WebSocket and shows PAUSED', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response(JSON.stringify(fixtureSnapshot), { status: 200 })))

  renderPage()
  await screen.findByText('Dow Jones Industrial Average')
  expect(FakeWebSocket.instances).toHaveLength(0)
  expect(screen.getByRole('status', { name: 'Live feed PAUSED' })).toBeInTheDocument()
})

test('all timeframes mode also opens no WebSocket while live refresh is paused', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response(JSON.stringify(fixtureSnapshot), { status: 200 })))

  renderPage()
  await screen.findByText('Dow Jones Industrial Average')
  fireEvent.click(screen.getByRole('switch', { name: 'Analysis mode: all timeframes' }))

  await screen.findByRole('table', { name: 'All timeframes market instruments' })
  expect(FakeWebSocket.instances).toHaveLength(0)
})
