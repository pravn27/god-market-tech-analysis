import { Descriptions, Drawer, Tag, Typography } from 'antd'

import type { GlobalMarketInstrument } from '../../api/client'
import { formatChange, formatPrice, freshnessColor, sourceColor, sourceLabel } from './marketFormat'

interface MarketInstrumentDetailDrawerProps {
  instrument: GlobalMarketInstrument | null
  onClose: () => void
}

const directionColor: Record<GlobalMarketInstrument['direction'], string> = {
  advancing: 'success',
  declining: 'error',
  unchanged: 'default',
  unavailable: 'warning',
}

export default function MarketInstrumentDetailDrawer({ instrument, onClose }: MarketInstrumentDetailDrawerProps) {
  return (
    <Drawer
      open={instrument !== null}
      title={instrument ? `Market evidence: ${instrument.display_name}` : 'Market evidence'}
      onClose={onClose}
      size="default"
    >
      {instrument && (
        <>
          <Descriptions column={1} size="small" bordered items={[
            { key: 'symbol', label: 'Symbol', children: instrument.symbol },
            { key: 'last', label: 'Last', children: formatPrice(instrument.last_price) },
            { key: 'change', label: 'Daily change', children: formatChange(instrument.change_percent) },
            { key: 'direction', label: 'Direction', children: <Tag color={directionColor[instrument.direction]}>{instrument.direction.toUpperCase()}</Tag> },
            { key: 'freshness', label: 'Freshness', children: <Tag color={freshnessColor[instrument.freshness_state]}>{instrument.freshness_state.replace('_', ' ').toUpperCase()}</Tag> },
            { key: 'source', label: 'Source', children: <Tag color={sourceColor[instrument.source]}>{sourceLabel[instrument.source]}</Tag> },
            { key: 'observed', label: 'Observed', children: instrument.source_timestamp ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(instrument.source_timestamp)) : '—' },
          ]} />
          <div className="instrument-evidence-notes">
            <Typography.Title level={5}>Evidence notes</Typography.Title>
            {instrument.unavailable_reason && <Typography.Paragraph>{instrument.unavailable_reason}</Typography.Paragraph>}
            {instrument.warnings.map((warning) => <Typography.Paragraph key={warning}>{warning}</Typography.Paragraph>)}
            {!instrument.unavailable_reason && instrument.warnings.length === 0 && (
              <Typography.Paragraph type="secondary">Current evidence is available. This dashboard does not provide a trade instruction.</Typography.Paragraph>
            )}
          </div>
        </>
      )}
    </Drawer>
  )
}
