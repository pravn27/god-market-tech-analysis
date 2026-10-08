import { FallOutlined, RiseOutlined } from '@ant-design/icons'
import { Tag, Typography } from 'antd'

import type { GlobalMarketGroup } from '../../api/client'
import { calculateSentiment, sentimentTagColor } from './marketFormat'

interface MarketGroupHeaderProps {
  group: GlobalMarketGroup
}

export default function MarketGroupHeader({ group }: MarketGroupHeaderProps) {
  const { dominantLabel, dominantPercent, total } = calculateSentiment(group.instruments)
  const count = group.instruments.length

  return (
    <div className="market-group-header">
      <div className="market-group-title">
        <Typography.Title id={`group-${group.name}`} level={3}>{group.name}</Typography.Title>
        <Typography.Text type="secondary">{count} {count === 1 ? 'item' : 'items'}</Typography.Text>
      </div>
      {total > 0 && (
        <Tag
          color={sentimentTagColor[dominantLabel]}
          icon={dominantLabel === 'Bullish' ? <RiseOutlined /> : dominantLabel === 'Bearish' ? <FallOutlined /> : undefined}
          className="market-group-sentiment"
        >
          {dominantPercent}% {dominantLabel}
        </Tag>
      )}
    </div>
  )
}
