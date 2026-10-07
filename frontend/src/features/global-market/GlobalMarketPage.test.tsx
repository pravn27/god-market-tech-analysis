import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import GlobalMarketPage from './GlobalMarketPage'

const fixtureSnapshot = {
  watchlist_name: 'PS_Global_Indices',
  read_at: '2026-10-06T12:00:00Z',
  timeframe: 'daily',
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

afterEach(() => vi.restoreAllMocks())

test('renders breadth, ordered groups, fixture warning, and unavailable evidence', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(fixtureSnapshot), { status: 200 })))

  renderPage()

  expect(await screen.findByRole('heading', { name: 'USA' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'INDIA ADRS' })).toBeInTheDocument()
  expect(screen.getByText('Dow Jones Industrial Average')).toBeInTheDocument()
  expect(screen.getByText(/Fixture data only/i)).toBeInTheDocument()
  const unavailableCard = screen.getByText('Unavailable').closest('.ant-card')
  expect(within(unavailableCard as HTMLElement).getByText('1')).toBeInTheDocument()
  expect(screen.getByText(/Fixture does not include a current value/i)).toBeInTheDocument()
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
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/global-market-sentiment?timeframe=daily')
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

  expect((await screen.findAllByText('DESKTOP ASSISTED')).length).toBeGreaterThan(0)
  fireEvent.click(screen.getByRole('button', { name: 'Cards' }))
  expect(screen.getAllByText('DESKTOP ASSISTED')).toHaveLength(2)
})

test('filters sections, switches to cards, and opens read-only evidence details', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(fixtureSnapshot), { status: 200 })))

  renderPage()

  await screen.findByText('Dow Jones Industrial Average')
  fireEvent.change(screen.getByLabelText('Market section'), { target: { value: 'INDIA ADRS' } })
  expect(screen.queryByText('Dow Jones Industrial Average')).not.toBeInTheDocument()
  expect(screen.getByText('Infosys ADR')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Cards' }))
  fireEvent.click(screen.getByRole('button', { name: 'View evidence' }))
  expect(await screen.findByText('Market evidence: Infosys ADR')).toBeInTheDocument()
  expect(screen.getByText(/Fixture does not include a current value/i)).toBeInTheDocument()
})
