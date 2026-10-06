import { ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Skeleton, Space, Typography } from 'antd'
import { useState } from 'react'

import type { GlobalMarketInstrument } from '../../api/client'
import MarketGroupCards from './MarketGroupCards'
import MarketInstrumentDetailDrawer from './MarketInstrumentDetailDrawer'
import MarketGroupTable from './MarketGroupTable'
import SentimentSummary from './SentimentSummary'
import { useGlobalMarket } from './useGlobalMarket'

function formatReadAt(readAt: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(readAt))
}

export default function GlobalMarketPage() {
  const { data, error, isFetching, isPending, refetch } = useGlobalMarket('daily')
  const [section, setSection] = useState('all')
  const [view, setView] = useState<'table' | 'cards'>('table')
  const [selectedInstrument, setSelectedInstrument] = useState<GlobalMarketInstrument | null>(null)
  const visibleGroups = data?.groups.filter((group) => section === 'all' || group.name === section) ?? []

  return (
    <section aria-labelledby="global-market-heading" className="market-dashboard">
      <div className="page-title-row">
        <div>
          <Typography.Title id="global-market-heading" level={1}>Global Market</Typography.Title>
          <Typography.Paragraph type="secondary">
            Daily market context from the local God Market API. This is not a trade instruction.
          </Typography.Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          Refresh
        </Button>
      </div>

      {isPending && <Skeleton active paragraph={{ rows: 10 }} aria-label="Loading global market context" />}

      {error && (
        <Alert
          type="error"
          showIcon
          title="Global Market data is unavailable"
          description={error.message}
        />
      )}

      {data && (
        <Space orientation="vertical" size="large" className="market-dashboard-content">
          <Alert
            type={data.completeness === 'complete' ? 'info' : data.completeness === 'partial' ? 'warning' : 'error'}
            showIcon
            title={`${data.watchlist_name} · ${data.timeframe.toUpperCase()} · read ${formatReadAt(data.read_at)}`}
            description="Source and freshness labels identify the evidence state of every item."
          />
          {data.warnings.map((warning) => (
            <Alert key={warning} type="warning" showIcon title={warning} />
          ))}
          <SentimentSummary snapshot={data} />
          {data.groups.length === 0 ? (
            <Empty description="No watchlist groups are available from the local API." />
          ) : (
            <>
              <div className="market-display-controls" aria-label="Global Market display controls">
                <label className="section-filter-label">
                  <span>Section</span>
                  <select aria-label="Market section" value={section} onChange={(event) => setSection(event.target.value)}>
                    <option value="all">All sections</option>
                    {data.groups.map((group) => <option key={group.name} value={group.name}>{group.name}</option>)}
                  </select>
                </label>
                <div className="view-choice" aria-label="Market view">
                  <Button type={view === 'table' ? 'primary' : 'default'} aria-pressed={view === 'table'} onClick={() => setView('table')}>Table</Button>
                  <Button type={view === 'cards' ? 'primary' : 'default'} aria-pressed={view === 'cards'} onClick={() => setView('cards')}>Cards</Button>
                </div>
              </div>
              {visibleGroups.length === 0 ? (
                <Empty description="No instruments match this section." />
              ) : visibleGroups.map((group) => view === 'table'
                ? <MarketGroupTable key={group.name} group={group} onSelect={setSelectedInstrument} />
                : <MarketGroupCards key={group.name} group={group} onSelect={setSelectedInstrument} />,
              )}
            </>
          )}
        </Space>
      )}
      <MarketInstrumentDetailDrawer instrument={selectedInstrument} onClose={() => setSelectedInstrument(null)} />
    </section>
  )
}
