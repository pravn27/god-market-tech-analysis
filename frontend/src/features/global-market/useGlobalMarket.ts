import { useQuery } from '@tanstack/react-query'

import { getGlobalMarketSentiment } from '../../api/client'

export function useGlobalMarket(timeframe = 'daily') {
  return useQuery({
    queryKey: ['global-market-sentiment', timeframe],
    queryFn: ({ signal }) => getGlobalMarketSentiment(timeframe, signal),
  })
}
