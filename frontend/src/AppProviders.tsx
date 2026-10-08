import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider } from 'antd'
import { useEffect, type ReactNode } from 'react'
import { BrowserRouter } from 'react-router-dom'

import { useUiStore } from './state/uiStore'
import { getAppTheme } from './theme'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export default function AppProviders({ children }: { children: ReactNode }) {
  const themeMode = useUiStore((state) => state.themeMode)

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
  }, [themeMode])

  return (
    <ConfigProvider theme={getAppTheme(themeMode)}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>{children}</BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  )
}
