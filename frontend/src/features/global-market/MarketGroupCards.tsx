import { Button, Card, Tag, Typography } from 'antd'

import type { GlobalMarketGroup, GlobalMarketInstrument } from '../../api/client'

interface MarketGroupCardsProps {
  group: GlobalMarketGroup
  onSelect: (instrument: GlobalMarketInstrument) => void
}

const directionColor: Record<GlobalMarketInstrument['direction'], string> = {
  advancing: 'success',
  declining: 'error',
  unchanged: 'default',
  unavailable: 'warning',
}

function formatPrice(value: number | null) {
  return value?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? '—'
}

function formatChange(value: number | null) {
  return value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

export default function MarketGroupCards({ group, onSelect }: MarketGroupCardsProps) {
  return (
    <section aria-labelledby={`group-${group.name}`} className="market-group">
      <Typography.Title id={`group-${group.name}`} level={3}>{group.name}</Typography.Title>
      {group.instruments.length === 0 ? (
        <Typography.Text type="secondary">No instruments in this watchlist section.</Typography.Text>
      ) : (
        <div className="market-card-grid">
          {group.instruments.map((instrument) => (
            <Card
              key={instrument.symbol}
              size="small"
              title={instrument.display_name}
              extra={<Tag color={directionColor[instrument.direction]}>{instrument.direction.toUpperCase()}</Tag>}
            >
              <Typography.Text type="secondary">{instrument.symbol}</Typography.Text>
              <dl className="instrument-card-values">
                <div><dt>Last</dt><dd>{formatPrice(instrument.last_price)}</dd></div>
                <div><dt>Daily change</dt><dd>{formatChange(instrument.change_percent)}</dd></div>
              </dl>
              <Button type="link" className="instrument-detail-link" onClick={() => onSelect(instrument)}>
                View evidence
              </Button>
            </Card>
          ))}
        </div>
      )}
    </section>
  )
}
