import { NodeIndexOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Select, Skeleton, Space, Tag, Typography } from 'antd'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import ChecklistMatrix, { type MatrixSelection } from './ChecklistMatrix'
import DecisionStrip from './DecisionStrip'
import MatrixDetailDrawer from './MatrixDetailDrawer'
import { formatTimestamp } from './mtfFormat'
import { useMtfAnalysis, useMtfInstruments } from './useMultiTimeframe'

const completenessColor = {
  complete: 'success',
  partial: 'warning',
  unavailable: 'error',
} as const

export default function MultiTimeframePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const instruments = useMtfInstruments()
  const catalog = instruments.data
  const knownSymbols = new Set(catalog?.sections.flatMap((section) => section.instruments.map((item) => item.symbol)))
  const requested = searchParams.get('symbol')?.toUpperCase() ?? null
  const symbol = catalog ? (requested && knownSymbols.has(requested) ? requested : catalog.default_symbol) : null
  const analysis = useMtfAnalysis(symbol)
  const [selection, setSelection] = useState<MatrixSelection | null>(null)
  const data = analysis.data
  const error = instruments.error ?? analysis.error ?? analysis.refreshError

  return (
    <section aria-labelledby="mtf-heading" className="market-dashboard mtf-page">
      <Space orientation="vertical" size="large" className="market-dashboard-content">
        <Card className="market-hero">
          <NodeIndexOutlined className="market-hero-icon" aria-hidden="true" />
          <div>
            <Typography.Title id="mtf-heading" level={3}>Multi-Timeframe Analysis</Typography.Title>
            <Typography.Text type="secondary">
              PAPA + SMM checklist across Super TIDE, TIDE, WAVE and RIPPLE · evidence for manual analysis, not a trade instruction.
            </Typography.Text>
          </div>
        </Card>

        <Card className="market-controls-card">
          <div className="market-display-controls" aria-label="Multi-timeframe controls">
            <div className="market-controls-left">
              <div className="market-control-group">
                <label className="market-control-label" htmlFor="mtf-instrument">Instrument</label>
                <Select
                  id="mtf-instrument"
                  className="mtf-instrument-select"
                  aria-label="Instrument"
                  loading={instruments.isPending}
                  value={symbol ?? undefined}
                  onChange={(value: string) => {
                    setSelection(null)
                    setSearchParams({ symbol: value })
                  }}
                  showSearch={{ optionFilterProp: 'searchText' }}
                  options={catalog?.sections.map((section) => ({
                    label: section.name,
                    title: section.name,
                    options: section.instruments.map((item) => ({
                      value: item.symbol,
                      label: item.display_name === item.symbol.split(':').at(-1)
                        ? item.symbol
                        : `${item.display_name} (${item.symbol})`,
                      searchText: `${item.display_name} ${item.symbol}`,
                    })),
                  }))}
                />
              </div>
              {catalog && (
                <div className="market-control-group">
                  <span className="market-control-label">Watchlist</span>
                  <Tag color="blue" className="daily-context-tag">{catalog.watchlist_name}</Tag>
                </div>
              )}
            </div>
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              loading={analysis.isRefreshing || (analysis.isFetching && !analysis.isPending)}
              disabled={!symbol}
              onClick={() => void analysis.forceRefresh()}
            >
              Refresh Data
            </Button>
          </div>
        </Card>

        {error && <Alert type="error" showIcon title="Multi-timeframe analysis is unavailable" description={error.message} />}

        {symbol && analysis.isPending && (
          <Card><Skeleton active paragraph={{ rows: 12 }} aria-label="Loading multi-timeframe analysis" /></Card>
        )}

        {data && (
          <>
            <div className="market-snapshot-meta">
              <Typography.Text type="secondary">
                {data.display_name} · {data.symbol} · calculated {formatTimestamp(data.requested_at)} · profile {data.profile_version}
              </Typography.Text>
              <Tag color={completenessColor[data.completeness]}>{data.completeness.toUpperCase()}</Tag>
            </div>
            {data.warnings.length > 0 && (
              <Alert
                type="warning"
                showIcon
                title={`${data.warnings.length} timeframe note${data.warnings.length === 1 ? '' : 's'}`}
                description={(
                  <ul className="market-warning-list">
                    {data.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                  </ul>
                )}
              />
            )}
            <DecisionStrip analysis={data} />
            <Card className="mtf-matrix-card">
              <ChecklistMatrix analysis={data} onSelect={setSelection} />
            </Card>
            <MatrixDetailDrawer analysis={data} selection={selection} onClose={() => setSelection(null)} />
          </>
        )}
      </Space>
    </section>
  )
}
