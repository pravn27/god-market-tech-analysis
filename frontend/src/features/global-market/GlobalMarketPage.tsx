import { AppstoreOutlined, GlobalOutlined, ReloadOutlined, TableOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Segmented, Skeleton, Space, Tag, Typography } from 'antd'
import { useState } from 'react'

import type { GlobalMarketInstrument } from '../../api/client'
import MarketGroupCards from './MarketGroupCards'
import MarketInstrumentDetailDrawer from './MarketInstrumentDetailDrawer'
import MarketGroupTable from './MarketGroupTable'
import SentimentSummary from './SentimentSummary'
import { useGlobalMarket } from './useGlobalMarket'

const completenessColor = {
  complete: 'success',
  partial: 'warning',
  unavailable: 'error',
} as const

function formatReadAt(readAt: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(readAt))
}

export default function GlobalMarketPage() {
  const { data, error, isFetching, isPending, refetch } = useGlobalMarket('daily')
  const [view, setView] = useState<'cards' | 'table'>('cards')
  const [selectedInstrument, setSelectedInstrument] = useState<GlobalMarketInstrument | null>(null)
  const desktopAssistedCount = data?.groups
    .flatMap((group) => group.instruments)
    .filter((instrument) => instrument.source === 'desktop_bridge').length ?? 0

  return (
    <section aria-labelledby="global-market-heading" className="market-dashboard">
      <Space orientation="vertical" size="large" className="market-dashboard-content">
        <Card className="market-hero">
          <GlobalOutlined className="market-hero-icon" aria-hidden="true" />
          <div>
            <Typography.Title id="global-market-heading" level={3}>Global Markets</Typography.Title>
            <Typography.Text type="secondary">
              Daily world indices &amp; market sentiment · evidence for manual analysis, not a trade instruction.
            </Typography.Text>
          </div>
        </Card>

        <Card className="market-controls-card">
          <div className="market-display-controls" aria-label="Global Market display controls">
            <div className="market-controls-left">
              <div className="market-control-group">
                <span className="market-control-label">Timeframe</span>
                <Tag color="blue" className="daily-context-tag">Daily snapshot</Tag>
              </div>
              <div className="market-control-group">
                <span className="market-control-label">View Mode</span>
                <Segmented
                  aria-label="Market view"
                  value={view}
                  onChange={(value) => setView(value as 'cards' | 'table')}
                  options={[
                    { label: 'Cards', value: 'cards', icon: <AppstoreOutlined /> },
                    { label: 'Table', value: 'table', icon: <TableOutlined /> },
                  ]}
                />
              </div>
            </div>
            <Button type="primary" icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
              Refresh Data
            </Button>
          </div>
        </Card>

        {isPending && (
          <Card><Skeleton active paragraph={{ rows: 10 }} aria-label="Loading global market context" /></Card>
        )}

        {error && (
          <Alert type="error" showIcon title="Global Market data is unavailable" description={error.message} />
        )}

        {data && (
          <>
            <div className="market-snapshot-meta">
              <Typography.Text type="secondary">
                {data.watchlist_name} · {data.timeframe.toUpperCase()} · read {formatReadAt(data.read_at)}
              </Typography.Text>
              <Tag color={completenessColor[data.completeness]}>{data.completeness.toUpperCase()}</Tag>
            </div>
            {data.desktop_fallback === 'full' && (
              <Alert
                type="warning"
                showIcon
                title="Official TradingView MCP is unavailable · showing TradingView Desktop watchlist quotes"
                description="Desktop quotes carry the local read time, not an exchange timestamp. Official data returns automatically on the next refresh once the MCP recovers."
              />
            )}
            {data.desktop_fallback === 'partial' && (
              <Alert
                type="info"
                showIcon
                title={`TradingView Desktop watchlist filled ${desktopAssistedCount} item${desktopAssistedCount === 1 ? '' : 's'} the official MCP could not supply`}
                description="Those cards are tagged DESKTOP ASSISTED; open one for the official failure reason."
              />
            )}
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
            {data.groups.length === 0 ? (
              <Card><Empty description="No watchlist groups are available from the local API." /></Card>
            ) : (
              <>
                <SentimentSummary snapshot={data} />
                {data.groups.map((group) => view === 'table'
                  ? <MarketGroupTable key={group.name} group={group} onSelect={setSelectedInstrument} />
                  : <MarketGroupCards key={group.name} group={group} onSelect={setSelectedInstrument} />,
                )}
              </>
            )}
          </>
        )}
      </Space>
      <MarketInstrumentDetailDrawer instrument={selectedInstrument} onClose={() => setSelectedInstrument(null)} />
    </section>
  )
}
