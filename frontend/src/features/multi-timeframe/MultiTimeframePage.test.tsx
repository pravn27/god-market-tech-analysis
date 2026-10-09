import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

import type { AnalysisTimeframe, MultiTimeframeAnalysis, MtfInstrumentCatalog } from '../../api/client'
import MultiTimeframePage from './MultiTimeframePage'

const catalog: MtfInstrumentCatalog = {
  watchlist_name: 'PS_DailyWatch_Favourite',
  recorded_at: '2026-10-09T10:07:27Z',
  default_symbol: 'NSE:NIFTY',
  sections: [
    { name: 'F & O', instruments: [{ symbol: 'NSE:NIFTY', display_name: 'Nifty 50' }] },
    { name: 'DAILY_WATCHLIST 2024 JAN', instruments: [{ symbol: 'NSE:RELIANCE', display_name: 'RELIANCE' }] },
  ],
}

const timeframes: AnalysisTimeframe[] = ['monthly', 'weekly', 'daily', '4h', '1h', '15m']

function status(timeframe: AnalysisTimeframe) {
  const missing = timeframe === '15m'
  return {
    timeframe,
    source: missing ? null : 'official_mcp' as const,
    source_timestamp: missing ? null : '2026-10-09T09:15:00Z',
    freshness_state: missing ? 'unavailable' as const : 'ready' as const,
    live_candle: timeframe === 'daily',
    last_close: missing ? null : 25100.5,
    candle_count: missing ? 0 : 500,
    unavailable_reason: missing ? 'Source is unavailable for this timeframe.' : null,
  }
}

function analysisFor(symbol: string, displayName: string): MultiTimeframeAnalysis {
  const macdCells = Object.fromEntries(timeframes.map((tf) => [tf, tf === '15m'
    ? { labels: [], bias: 'unavailable' as const, values: {}, rule_ids: ['macd'], unavailable_reason: 'Source is unavailable for this timeframe.' }
    : { labels: ['(PCO) Buy Signal below Zero Line', 'PCO state', 'Up Tick'], bias: 'bullish' as const, values: { macd: -12.5, signal: -14 }, rule_ids: ['macd'], unavailable_reason: null }]))
  const screen = { signal: 'BUY' as const, labels: ['Up Tick', 'PCO state'], unavailable_reason: null }
  const missing = { signal: 'UNAVAILABLE' as const, labels: [], unavailable_reason: 'Source is unavailable for this timeframe.' }
  return {
    symbol,
    display_name: displayName,
    requested_at: '2026-10-09T10:20:00Z',
    profile_version: 'mtf-checklist-v1',
    completeness: 'partial',
    timeframes: Object.fromEntries(timeframes.map((tf) => [tf, status(tf)])),
    layers: [
      { name: 'Super TIDE', timeframes: ['monthly', 'weekly'], screen_indicator: 'MACD', signal: 'BUY', screens: { monthly: screen, weekly: screen }, missing_timeframes: [] },
      { name: 'TIDE', timeframes: ['daily', '4h'], screen_indicator: 'MACD', signal: 'BUY', screens: { daily: screen, '4h': screen }, missing_timeframes: [] },
      { name: 'WAVE', timeframes: ['4h', '1h'], screen_indicator: 'Stochastic / RSI', signal: 'BUY', screens: { '4h': screen, '1h': screen }, missing_timeframes: [] },
      { name: 'RIPPLE', timeframes: ['1h', '15m'], screen_indicator: 'MACD', signal: 'UNAVAILABLE', screens: { '1h': screen, '15m': missing }, missing_timeframes: ['15m'] },
    ],
    rows: [
      { id: 'macd', section: '3. Check Indicators', label: 'MACD', automated: true, cells: macdCells },
      { id: 'what_if', section: '5. Concepts / Setups / Confirmation', label: 'Be ready with What If analysis', automated: false, cells: {} },
    ],
    decisions: {
      double_screens: [
        { name: 'Double Screen (TIDE + WAVE)', layers: ['TIDE', 'WAVE'], decision: 'BUY', position_note: null, missing_timeframes: [] },
        { name: 'Double Screen (Super TIDE + TIDE)', layers: ['Super TIDE', 'TIDE'], decision: 'BUY', position_note: null, missing_timeframes: [] },
        { name: 'Double Screen (WAVE + RIPPLE)', layers: ['WAVE', 'RIPPLE'], decision: 'INCOMPLETE — 15m unavailable', position_note: null, missing_timeframes: ['15m'] },
      ],
      triple_screen: { name: 'Triple Screen (TIDE + WAVE + RIPPLE)', layers: ['TIDE', 'WAVE', 'RIPPLE'], decision: 'INCOMPLETE — 15m unavailable', position_note: null, missing_timeframes: ['15m'] },
      disclaimer: 'Checklist signal derived from the SMM Double/Triple Screen rules — not financial advice.',
    },
    warnings: ['15m: Source is unavailable for this timeframe.'],
  }
}

function mockApi() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/mtf-analysis/instruments')) return new Response(JSON.stringify(catalog), { status: 200 })
    if (url.includes('NSE%3ARELIANCE')) return new Response(JSON.stringify(analysisFor('NSE:RELIANCE', 'RELIANCE')), { status: 200 })
    return new Response(JSON.stringify(analysisFor('NSE:NIFTY', 'Nifty 50')), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderPage(path = '/multi-timeframe') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <MultiTimeframePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('defaults to Nifty 50 and renders decisions, eight timeframe columns, and manual rows', async () => {
  const fetchMock = mockApi()
  renderPage()

  expect(await screen.findByText(/Nifty 50 · NSE:NIFTY/)).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/mtf-analysis/NSE%3ANIFTY?refresh_mode=prefer_cache'), expect.anything())

  const decisions = screen.getByRole('region', { name: 'Screen decisions' })
  expect(within(decisions).getByText('Double Screen (TIDE + WAVE)')).toBeInTheDocument()
  expect(within(decisions).getAllByText('INCOMPLETE — 15m unavailable')).toHaveLength(2)
  expect(within(decisions).getByText(/not financial advice/)).toBeInTheDocument()

  const matrix = screen.getByRole('region', { name: 'Multi-timeframe checklist' })
  expect(within(matrix).getAllByRole('columnheader').filter((header) => /^(Monthly|Weekly|Daily|4H|1H|15m)/.test(header.textContent ?? ''))).toHaveLength(8)
  expect(within(matrix).getAllByText('Manual check')).toHaveLength(8)
  expect(within(matrix).getAllByText('Live candle')).toHaveLength(1)
  expect(within(matrix).getAllByText('Unavailable').length).toBeGreaterThan(0)
  expect(screen.getByText('1 timeframe note')).toBeInTheDocument()

  const sectionHeaders = within(matrix).getAllByRole('rowheader')
    .map((header) => header.textContent ?? '')
    .filter((text) => /^\d\./.test(text))
  expect(sectionHeaders).toEqual([
    '3. Check Indicators',
    '4. Double & Triple Screen decision',
    '5. Concepts / Setups / Confirmation',
  ])
})

test('opens the detail drawer with values when a cell is clicked', async () => {
  mockApi()
  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: /^MACD, TIDE Daily/ }))

  const drawer = await screen.findByRole('dialog')
  expect(within(drawer).getByText('MACD · TIDE Daily')).toBeInTheDocument()
  expect(within(drawer).getByText('-12.5')).toBeInTheDocument()
  expect(within(drawer).getByText(/live, still forming/)).toBeInTheDocument()
})

test('uses the symbol from the URL when it is in the watchlist snapshot', async () => {
  const fetchMock = mockApi()
  renderPage('/multi-timeframe?symbol=NSE:RELIANCE')

  expect(await screen.findByText(/RELIANCE · NSE:RELIANCE/)).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('NSE%3ANIFTY'), expect.anything())
})

test('falls back to the default instrument for a symbol outside the snapshot', async () => {
  mockApi()
  renderPage('/multi-timeframe?symbol=NSE:TCS')

  expect(await screen.findByText(/Nifty 50 · NSE:NIFTY/)).toBeInTheDocument()
})

test('Refresh Data forces a source refresh', async () => {
  const fetchMock = mockApi()
  renderPage()
  await screen.findByText(/Nifty 50 · NSE:NIFTY/)

  fireEvent.click(screen.getByRole('button', { name: /Refresh Data/ }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining('/mtf-analysis/NSE%3ANIFTY?refresh_mode=force_refresh'),
    expect.anything(),
  ))
})
