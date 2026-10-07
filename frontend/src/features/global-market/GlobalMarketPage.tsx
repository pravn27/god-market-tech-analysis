import { AppstoreOutlined, GlobalOutlined, ReloadOutlined, TableOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Segmented, Select, Skeleton, Space, Tag, Typography } from 'antd'
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
      <Card className="market-hero">
        <GlobalOutlined className="market-hero-icon" aria-hidden="true" />
        <div>
          <Typography.Title id="global-market-heading" level={1}>Global Markets</Typography.Title>
          <Typography.Paragraph type="secondary">
            Daily world indices and market context · evidence for manual analysis, not a trade instruction.
          </Typography.Paragraph>
        </div>
      </Card>

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
          {data.groups.length > 0 && (
            <Card className="market-controls-card" size="small">
              <div className="market-display-controls" aria-label="Global Market display controls">
                <div className="market-control-group">
                  <label className="section-filter-label" htmlFor="market-section-select">Market section</label>
                  <Select
                    id="market-section-select"
                    aria-label="Market section"
                    value={section}
                    onChange={(value) => setSection(String(value))}
                    options={[
                      { label: 'All sections', value: 'all' },
                      ...data.groups.map((group) => ({ label: group.name, value: group.name })),
                    ]}
                    className="market-section-select"
                  />
                </div>
                <div className="market-controls-right">
                  <Tag color="blue" className="daily-context-tag">Daily snapshot</Tag>
                  <div className="market-control-group">
                    <span className="section-filter-label">View</span>
                    <Segmented
                      aria-label="Market view"
                      value={view}
                      onChange={(value) => setView(value as 'table' | 'cards')}
                      options={[
                        { label: 'Table', value: 'table', icon: <TableOutlined /> },
                        { label: 'Cards', value: 'cards', icon: <AppstoreOutlined /> },
                      ]}
                    />
                  </div>
                  <Button type="primary" icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
                    Refresh data
                  </Button>
                </div>
              </div>
            </Card>
          )}
          <Alert
            type={data.completeness === 'complete' ? 'info' : data.completeness === 'partial' ? 'warning' : 'error'}
            showIcon
            title={`${data.watchlist_name} · ${data.timeframe.toUpperCase()} · read ${formatReadAt(data.read_at)}`}
            description="Source and freshness labels identify the evidence state of every item."
          />
          {data.warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              title={`${data.warnings.length} data note${data.warnings.length === 1 ? '' : 's'}`}
              description={(
                <ul className="market-warning-list">
                  {data.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                </ul>
              )}
            />
          )}
          <SentimentSummary snapshot={data} />
          {data.groups.length === 0 ? (
            <Empty description="No watchlist groups are available from the local API." />
          ) : (
            <>
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
