import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getMtfAnalysis, getMtfInstruments } from '../../api/client'

export function useMtfInstruments() {
  return useQuery({
    queryKey: ['mtf-instruments'],
    queryFn: ({ signal }) => getMtfInstruments(signal),
    staleTime: Infinity,
  })
}

export function useMtfAnalysis(symbol: string | null) {
  const queryClient = useQueryClient()
  const [refreshError, setRefreshError] = useState<Error | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const queryKey = ['mtf-analysis', symbol]
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => getMtfAnalysis(symbol as string, 'prefer_cache', signal),
    enabled: symbol !== null,
  })

  async function forceRefresh() {
    if (!symbol) return
    setIsRefreshing(true)
    setRefreshError(null)
    try {
      queryClient.setQueryData(queryKey, await getMtfAnalysis(symbol, 'force_refresh'))
    } catch (error) {
      setRefreshError(error as Error)
    } finally {
      setIsRefreshing(false)
    }
  }

  return { ...query, forceRefresh, isRefreshing, refreshError }
}
