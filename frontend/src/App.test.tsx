import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'

import App from './App'
import { useUiStore } from './state/uiStore'

function renderApp() {
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
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  useUiStore.setState({ themeMode: 'light' })
})

test('renders the Global Market route shell', () => {
  renderApp()

  expect(screen.getByRole('heading', { name: 'Global Markets' })).toBeInTheDocument()
  expect(screen.getByText(/manual analysis/i)).toBeInTheDocument()
  expect(screen.getByRole('navigation', { name: 'Primary' })).toHaveTextContent('Global Market')
})

test('toggles between light and dark themes and remembers the choice', () => {
  renderApp()

  fireEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
  expect(useUiStore.getState().themeMode).toBe('dark')
  expect(JSON.parse(localStorage.getItem('god-market-ui') ?? '{}').state.themeMode).toBe('dark')

  fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
  expect(useUiStore.getState().themeMode).toBe('light')
})
