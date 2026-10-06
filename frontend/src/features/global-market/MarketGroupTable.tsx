import { Button, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import type { GlobalMarketGroup, GlobalMarketInstrument } from '../../api/client'

interface MarketGroupTableProps {
  group: GlobalMarketGroup
  onSelect: (instrument: GlobalMarketInstrument) => void
}

const directionColor: Record<GlobalMarketInstrument['direction'], string> = {
  advancing: 'success',
  declining: 'error',
  unchanged: 'default',
  unavailable: 'warning',
}

const freshnessColor: Record<GlobalMarketInstrument['freshness_state'], string> = {
  ready: 'success',
  stale: 'warning',
  unavailable: 'error',
  not_configured: 'default',
}

const columns: ColumnsType<GlobalMarketInstrument> = [
  {
    title: 'Instrument',
    dataIndex: 'display_name',
    key: 'instrument',
    render: (displayName: string, item) => (
      <div>
        <Typography.Text strong>{displayName}</Typography.Text>
        <div><Typography.Text type="secondary">{item.symbol}</Typography.Text></div>
      </div>
    ),
  },
  {
    title: 'Last',
    dataIndex: 'last_price',
    key: 'last_price',
    align: 'right',
    render: (value: number | null) => value?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? '—',
  },
  {
    title: 'Change',
    dataIndex: 'change_percent',
    key: 'change_percent',
    align: 'right',
    render: (value: number | null) => value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`,
  },
  {
    title: 'Direction',
    dataIndex: 'direction',
    key: 'direction',
    render: (direction: GlobalMarketInstrument['direction']) => (
      <Tag color={directionColor[direction]}>{direction.toUpperCase()}</Tag>
    ),
  },
  {
    title: 'Freshness',
    dataIndex: 'freshness_state',
    key: 'freshness',
    render: (freshness: GlobalMarketInstrument['freshness_state']) => (
      <Tag color={freshnessColor[freshness]}>{freshness.replace('_', ' ').toUpperCase()}</Tag>
    ),
  },
  {
    title: 'Evidence note',
    key: 'note',
    render: (_, item) => item.unavailable_reason ?? (item.warnings.join(' ') || 'Current evidence available.'),
  },
]

export default function MarketGroupTable({ group, onSelect }: MarketGroupTableProps) {
  const tableColumns: ColumnsType<GlobalMarketInstrument> = [
    ...columns,
    {
      title: 'Details',
      key: 'details',
      render: (_, item) => <Button type="link" onClick={() => onSelect(item)}>View evidence</Button>,
    },
  ]

  return (
    <section aria-labelledby={`group-${group.name}`} className="market-group">
      <Typography.Title id={`group-${group.name}`} level={3}>{group.name}</Typography.Title>
      <Table
        aria-label={`${group.name} market instruments`}
        columns={tableColumns}
        dataSource={group.instruments}
        rowKey="symbol"
        pagination={false}
        size="middle"
        scroll={{ x: 780 }}
        locale={{ emptyText: 'No instruments in this watchlist section.' }}
      />
    </section>
  )
}
