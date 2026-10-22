import { useQueries, useQuery } from '@tanstack/react-query'

import { getGlobalMarketSentiment, type GlobalMarketTimeframe } from '../../api/client'
import { globalMarketTimeframes } from './marketFormat'

export function useGlobalMarket(timeframe: GlobalMarketTimeframe = '1D', enabled = true) {
  return useQuery({
    queryKey: ['global-market-sentiment', timeframe],
    queryFn: ({ signal }) => getGlobalMarketSentiment(timeframe, signal),
    enabled,
  })
}

/** One query per timeframe; shares cache entries with the single-timeframe query. */
export function useAllGlobalMarketTimeframes(enabled = true) {
  return useQueries({
    queries: globalMarketTimeframes.map(({ value }) => ({
      queryKey: ['global-market-sentiment', value],
      queryFn: ({ signal }: { signal: AbortSignal }) => getGlobalMarketSentiment(value, signal),
      enabled,
    })),
    combine: (results) => globalMarketTimeframes.map(({ value }, index) => ({
      timeframe: value,
      snapshot: results[index].data,
      error: results[index].error,
      pending: results[index].isPending,
      fetching: results[index].isFetching,
      refetch: results[index].refetch,
    })),
  })
}
