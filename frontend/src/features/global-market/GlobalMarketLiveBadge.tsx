import { Tag, Typography } from 'antd'

import type { GlobalMarketLiveState } from './useGlobalMarketLive'

const statusLabel = {
  live: 'LIVE',
  reconnecting: 'RECONNECTING',
  connecting: 'CONNECTING',
} as const

const statusColor = {
  live: 'success',
  reconnecting: 'warning',
  connecting: 'default',
} as const

function formatTime(value: Date) {
  return new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(value)
}

interface GlobalMarketLiveBadgeProps {
  state: GlobalMarketLiveState
}

/** Shows whether a timeframe's WebSocket feed is connected and when it last delivered a snapshot. */
export default function GlobalMarketLiveBadge({ state }: GlobalMarketLiveBadgeProps) {
  return (
    <span className="market-live-badge" role="status" aria-label={`Live feed ${statusLabel[state.status]}`}>
      <Tag color={statusColor[state.status]}>{statusLabel[state.status]}</Tag>
      {state.lastUpdate && (
        <Typography.Text type="secondary" className="sentiment-footnote">
          Updated {formatTime(state.lastUpdate)}
        </Typography.Text>
      )}
    </span>
  )
}
