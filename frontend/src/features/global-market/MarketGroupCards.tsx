import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons'
import { Card, Tag, Tooltip, Typography } from 'antd'

import type { GlobalMarketGroup, GlobalMarketInstrument } from '../../api/client'
import MarketGroupHeader from './MarketGroupHeader'
import {
  changeColor,
  changeTagColor,
  formatChange,
  formatPrice,
  shortSymbol,
  sourceColor,
  sourceLabel,
} from './marketFormat'

interface MarketGroupCardsProps {
  group: GlobalMarketGroup
  onSelect: (instrument: GlobalMarketInstrument) => void
}

function trendClass(change: number | null) {
  if (change === null || change === 0) return 'flat'
  return change > 0 ? 'up' : 'down'
}

function InstrumentCard({ instrument, onSelect }: { instrument: GlobalMarketInstrument; onSelect: () => void }) {
  const change = instrument.change_percent
  const ChangeIcon = change !== null && change > 0 ? ArrowUpOutlined : change !== null && change < 0 ? ArrowDownOutlined : null

  return (
    <Card
      hoverable
      size="small"
      role="button"
      tabIndex={0}
      aria-label={`View evidence for ${instrument.display_name}`}
      className={`instrument-card instrument-card-${trendClass(change)}`}
      style={{ borderLeftColor: changeColor(change) }}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect()
        }
      }}
    >
      <Typography.Text strong className="instrument-card-ticker">{shortSymbol(instrument.symbol)}</Typography.Text>
      <Typography.Text type="secondary" className="instrument-card-symbol">{instrument.symbol}</Typography.Text>
      <div className="instrument-card-price">{formatPrice(instrument.last_price)}</div>
      <div className="instrument-card-tags">
        {change === null ? (
          <Tooltip title={instrument.unavailable_reason ?? 'No current value'}>
            <Tag color="warning">Unavailable</Tag>
          </Tooltip>
        ) : (
          <Tag color={changeTagColor(change)} className="instrument-card-change">
            {ChangeIcon && <ChangeIcon />} {formatChange(change)}
          </Tag>
        )}
        {instrument.source !== 'official_mcp' && (
          <Tag color={sourceColor[instrument.source]}>{sourceLabel[instrument.source]}</Tag>
        )}
        {instrument.freshness_state === 'stale' && <Tag color="warning">STALE</Tag>}
      </div>
      <Typography.Text type="secondary" className="instrument-card-name" title={instrument.display_name}>
        {instrument.display_name}
      </Typography.Text>
    </Card>
  )
}

export default function MarketGroupCards({ group, onSelect }: MarketGroupCardsProps) {
  return (
    <Card aria-labelledby={`group-${group.name}`} className="market-group" title={<MarketGroupHeader group={group} />}>
      {group.instruments.length === 0 ? (
        <Typography.Text type="secondary">No instruments in this watchlist section.</Typography.Text>
      ) : (
        <div className="market-card-grid">
          {group.instruments.map((instrument) => (
            <InstrumentCard key={instrument.symbol} instrument={instrument} onSelect={() => onSelect(instrument)} />
          ))}
        </div>
      )}
    </Card>
  )
}
