import { AppstoreOutlined, GlobalOutlined, ReloadOutlined, TableOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Segmented, Select, Skeleton, Space, Switch, Tag, Typography } from 'antd'
import { useState } from 'react'

import type { GlobalMarketInstrument, GlobalMarketTimeframe } from '../../api/client'
import AllTimeframesView from './AllTimeframesView'
import GlobalMarketLiveBadge from './GlobalMarketLiveBadge'
import MarketGroupCards from './MarketGroupCards'
import MarketInstrumentDetailDrawer from './MarketInstrumentDetailDrawer'
import MarketGroupTable from './MarketGroupTable'
import SentimentSummary from './SentimentSummary'
import { globalMarketTimeframes, timeframeName } from './marketFormat'
import { useAllGlobalMarketTimeframes, useGlobalMarket } from './useGlobalMarket'
import { GLOBAL_MARKET_LIVE_ENABLED, initialLiveState, pausedLiveState, useGlobalMarketLive } from './useGlobalMarketLive'

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
  const [mode, setMode] = useState<'single' | 'all'>('single')
  const [timeframe, setTimeframe] = useState<GlobalMarketTimeframe>('1D')
  const [view, setView] = useState<'cards' | 'table'>('cards')
  const [selectedInstrument, setSelectedInstrument] = useState<GlobalMarketInstrument | null>(null)
  const isAll = mode === 'all'

  const single = useGlobalMarket(timeframe, !isAll)
  const allResults = useAllGlobalMarketTimeframes(isAll)
  // One WebSocket per timeframe on screen: a single socket in Single mode, one for each in All mode.
  const liveStates = useGlobalMarketLive(
    isAll ? globalMarketTimeframes.map(({ value }) => value) : [timeframe],
    GLOBAL_MARKET_LIVE_ENABLED,
  )
  const live = liveStates[timeframe] ?? (GLOBAL_MARKET_LIVE_ENABLED ? initialLiveState : pausedLiveState)
  const data = isAll ? undefined : single.data
  const error = isAll ? null : single.error
  const refreshing = isAll ? allResults.some((result) => result.fetching) : single.isFetching

  const refreshData = () => {
    if (isAll) allResults.forEach((result) => void result.refetch())
    else void single.refetch()
  }

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
              World indices &amp; market sentiment · evidence for manual analysis, not a trade instruction.
            </Typography.Text>
          </div>
        </Card>

        <Card className="market-controls-card">
          <div className="market-display-controls" aria-label="Global Market display controls">
            <div className="market-controls-left">
              <div className="market-control-group">
                <span className="market-control-label">Analysis Mode</span>
                <div className="market-mode-switch">
                  <Typography.Text className={isAll ? undefined : 'market-mode-active'}>Single</Typography.Text>
                  <Switch
                    aria-label="Analysis mode: all timeframes"
                    checked={isAll}
                    onChange={(checked) => setMode(checked ? 'all' : 'single')}
                  />
                  <Typography.Text className={isAll ? 'market-mode-active' : undefined}>All Timeframes</Typography.Text>
                </div>
              </div>
              <div className="market-control-group">
                <span className="market-control-label">Timeframe</span>
                <Select<GlobalMarketTimeframe>
                  aria-label="Timeframe"
                  value={timeframe}
                  disabled={isAll}
                  onChange={setTimeframe}
                  style={{ width: 160 }}
                  options={globalMarketTimeframes.map(({ value, label }) => ({ value, label }))}
                />
              </div>
              <div className="market-control-group">
                <span className="market-control-label">View Mode</span>
                <Segmented
                  aria-label="Market view"
                  value={view}
                  disabled={isAll}
                  onChange={(value) => setView(value as 'cards' | 'table')}
                  options={[
                    { label: 'Cards', value: 'cards', icon: <AppstoreOutlined /> },
                    { label: 'Table', value: 'table', icon: <TableOutlined /> },
                  ]}
                />
              </div>
            </div>
            <Button type="primary" icon={<ReloadOutlined />} loading={refreshing} onClick={refreshData}>
              Refresh Data
            </Button>
          </div>
        </Card>

        {isAll ? (
          <AllTimeframesView results={allResults} live={liveStates} />
        ) : (
          <>
            {single.isPending && (
              <Card><Skeleton active paragraph={{ rows: 10 }} aria-label="Loading global market context" /></Card>
            )}

            {error && (
              <Alert type="error" showIcon title="Global Market data is unavailable" description={error.message} />
            )}

            {data && (
              <>
                <div className="market-snapshot-meta">
                  <Typography.Text type="secondary">
                    {data.watchlist_name} · {timeframeName(data.timeframe)} · read {formatReadAt(data.read_at)}
                  </Typography.Text>
                  <Tag color={completenessColor[data.completeness]}>{data.completeness.toUpperCase()}</Tag>
                  <GlobalMarketLiveBadge state={live} />
                </div>
                {live.error && live.status !== 'paused' && (
                  <Alert type="warning" showIcon title="Live refresh failed" description={live.error} />
                )}
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
          </>
        )}
      </Space>
      <MarketInstrumentDetailDrawer instrument={selectedInstrument} onClose={() => setSelectedInstrument(null)} />
    </section>
  )
}
