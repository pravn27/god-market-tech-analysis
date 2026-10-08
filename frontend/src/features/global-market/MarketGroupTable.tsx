import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons'
import { Button, Card, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import type { GlobalMarketGroup, GlobalMarketInstrument } from '../../api/client'
import MarketGroupHeader from './MarketGroupHeader'
import {
  changeTagColor,
  formatChange,
  formatPrice,
  freshnessColor,
  shortSymbol,
  sourceColor,
  sourceLabel,
} from './marketFormat'

interface MarketGroupTableProps {
  group: GlobalMarketGroup
  onSelect: (instrument: GlobalMarketInstrument) => void
}

const byNullableNumber = (a: number | null, b: number | null) => (a ?? -Infinity) - (b ?? -Infinity)

const columns: ColumnsType<GlobalMarketInstrument> = [
  {
    title: 'Index',
    dataIndex: 'symbol',
    key: 'symbol',
    width: 130,
    render: (symbol: string) => (
      <div>
        <Typography.Text strong>{shortSymbol(symbol)}</Typography.Text>
        <div><Typography.Text type="secondary" className="table-symbol">{symbol}</Typography.Text></div>
      </div>
    ),
  },
  {
    title: 'Name',
    dataIndex: 'display_name',
    key: 'name',
    ellipsis: true,
  },
  {
    title: 'Price',
    dataIndex: 'last_price',
    key: 'last_price',
    align: 'right',
    width: 140,
    sorter: (a, b) => byNullableNumber(a.last_price, b.last_price),
    render: (value: number | null) => <span className="table-price">{formatPrice(value)}</span>,
  },
  {
    title: 'Change %',
    dataIndex: 'change_percent',
    key: 'change_percent',
    align: 'center',
    width: 130,
    sorter: (a, b) => byNullableNumber(a.change_percent, b.change_percent),
    render: (value: number | null, item) => {
      if (value === null) return <Tag color="warning" title={item.unavailable_reason ?? undefined}>Unavailable</Tag>
      const Icon = value > 0 ? ArrowUpOutlined : value < 0 ? ArrowDownOutlined : null
      return (
        <Tag color={changeTagColor(value)} className="table-change">
          {Icon && <Icon />} {formatChange(value)}
        </Tag>
      )
    },
  },
  {
    title: 'Source',
    dataIndex: 'source',
    key: 'source',
    width: 150,
    render: (source: GlobalMarketInstrument['source']) => <Tag color={sourceColor[source]}>{sourceLabel[source]}</Tag>,
  },
  {
    title: 'Freshness',
    dataIndex: 'freshness_state',
    key: 'freshness',
    width: 130,
    render: (freshness: GlobalMarketInstrument['freshness_state']) => (
      <Tag color={freshnessColor[freshness]}>{freshness.replace('_', ' ').toUpperCase()}</Tag>
    ),
  },
]

export default function MarketGroupTable({ group, onSelect }: MarketGroupTableProps) {
  const tableColumns: ColumnsType<GlobalMarketInstrument> = [
    ...columns,
    {
      title: 'Details',
      key: 'details',
      width: 110,
      render: (_, item) => (
        <Button type="link" size="small" onClick={() => onSelect(item)} aria-label={`View evidence for ${item.display_name}`}>
          Evidence
        </Button>
      ),
    },
  ]

  return (
    <Card
      aria-labelledby={`group-${group.name}`}
      className="market-group market-group-table"
      title={<MarketGroupHeader group={group} />}
      styles={{ body: { padding: 0 } }}
    >
      <Table
        aria-label={`${group.name} market instruments`}
        columns={tableColumns}
        dataSource={group.instruments}
        rowKey="symbol"
        pagination={false}
        size="middle"
        scroll={{ x: 900 }}
        rowClassName={(_, index) => (index % 2 === 1 ? 'table-row-striped' : '')}
        locale={{ emptyText: 'No instruments in this watchlist section.' }}
      />
    </Card>
  )
}
