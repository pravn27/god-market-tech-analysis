import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { expect, test, vi } from 'vitest'

import App from './App'

test('renders the Global Market route shell', () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    watchlist_name: 'PS_Global_Indices',
    read_at: '2026-10-06T12:00:00Z',
    timeframe: 'daily',
    completeness: 'unavailable',
    groups: [],
    breadth: { advancing: 0, declining: 0, unchanged: 0, unavailable: 0 },
    warnings: [],
  }), { status: 200 })))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>,
  )

  expect(screen.getByRole('heading', { name: 'Global Markets' })).toBeInTheDocument()
  expect(screen.getByText(/manual analysis/i)).toBeInTheDocument()
})
