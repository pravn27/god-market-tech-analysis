import { FallOutlined, RiseOutlined } from '@ant-design/icons'
import { Card, Col, Row, Skeleton, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo } from 'react'

import type { GlobalMarketInstrument, GlobalMarketSnapshot, GlobalMarketTimeframe } from '../../api/client'
import GlobalMarketLiveBadge from './GlobalMarketLiveBadge'
import {
  calculateSentiment,
  changeTagColor,
  formatChange,
  globalMarketTimeframes,
  sentimentTagColor,
  shortSymbol,
  timeframeName,
} from './marketFormat'
import { initialLiveState, type GlobalMarketLiveState } from './useGlobalMarketLive'

export interface TimeframeResult {
  timeframe: GlobalMarketTimeframe
  snapshot: GlobalMarketSnapshot | undefined
  error: Error | null
  pending: boolean
}

interface AllTimeframesViewProps {
  results: TimeframeResult[]
  live: Partial<Record<GlobalMarketTimeframe, GlobalMarketLiveState>>
}

interface MatrixRow {
  symbol: string
  displayName: string
  section: string
  sectionSpan: number
}

const shortLabel = (timeframe: GlobalMarketTimeframe) =>
  globalMarketTimeframes.find((item) => item.value === timeframe)?.short ?? timeframe

export default function AllTimeframesView({ results, live }: AllTimeframesViewProps) {
  // The instrument list is the same for every timeframe; use the daily snapshot when it has loaded.
  const baseSnapshot = (results.find((r) => r.timeframe === '1D' && r.snapshot) ?? results.find((r) => r.snapshot))?.snapshot

  const rows = useMemo<MatrixRow[]>(() => {
    if (!baseSnapshot) return []
    return baseSnapshot.groups.flatMap((group) =>
      group.instruments.map((instrument, index) => ({
        symbol: instrument.symbol,
        displayName: instrument.display_name,
        section: group.name,
        sectionSpan: index === 0 ? group.instruments.length : 0,
      })),
    )
  }, [baseSnapshot])

  const bySymbol = useMemo(
    () =>
      new Map(
        results.map((result) => [
          result.timeframe,
          new Map(
            (result.snapshot?.groups.flatMap((group) => group.instruments) ?? []).map((instrument) => [
              instrument.symbol,
              instrument,
            ]),
          ),
        ]),
      ),
    [results],
  )

  const columns: ColumnsType<MatrixRow> = [
    {
      title: 'Section',
      dataIndex: 'section',
      key: 'section',
      width: 150,
      onCell: (row) => ({ rowSpan: row.sectionSpan }),
      render: (section: string) => <Typography.Text strong>{section}</Typography.Text>,
    },
    {
      title: 'Index',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 220,
      render: (symbol: string, row) => (
        <div>
          <Typography.Text strong>{shortSymbol(symbol)}</Typography.Text>
          <div><Typography.Text type="secondary" className="table-symbol">{row.displayName}</Typography.Text></div>
        </div>
      ),
    },
    ...results.map<ColumnsType<MatrixRow>[number]>((result) => ({
      title: shortLabel(result.timeframe),
      key: result.timeframe,
      align: 'center',
      width: 110,
      render: (_: unknown, row: MatrixRow) => {
        const instrument: GlobalMarketInstrument | undefined = bySymbol.get(result.timeframe)?.get(row.symbol)
        if (instrument) {
          if (instrument.change_percent === null) {
            return <Tag color="warning" title={instrument.unavailable_reason ?? undefined}>—</Tag>
          }
          return <Tag color={changeTagColor(instrument.change_percent)}>{formatChange(instrument.change_percent)}</Tag>
        }
        if (result.error) return <Tag color="error" title={result.error.message}>Unavailable</Tag>
        return <Skeleton.Input active size="small" style={{ width: 64 }} />
      },
    })),
  ]

  return (
    <section aria-label="All timeframes" className="all-timeframes">
      <Row gutter={[12, 12]} className="all-timeframes-summary">
        {results.map((result) => {
          const sentiment = result.snapshot ? calculateSentiment(result.snapshot.groups.flatMap((g) => g.instruments)) : null
          return (
            <Col xs={12} md={8} xl={4} key={result.timeframe}>
              <Card size="small" className="all-timeframe-card">
                <Typography.Text type="secondary">{timeframeName(result.timeframe)}</Typography.Text>
                <div>
                  <GlobalMarketLiveBadge state={live[result.timeframe] ?? initialLiveState} />
                </div>
                {sentiment ? (
                  <div className="all-timeframe-value">
                    <Tag color={sentimentTagColor[sentiment.dominantLabel]}>
                      {sentiment.dominantLabel === 'Bullish' && <RiseOutlined />}
                      {sentiment.dominantLabel === 'Bearish' && <FallOutlined />}
                      {' '}{sentiment.dominantPercent}% {sentiment.dominantLabel}
                    </Tag>
                    <div>
                      <Typography.Text type="secondary" className="sentiment-footnote">
                        {sentiment.bullish} up · {sentiment.bearish} down · {sentiment.unavailable} unavailable
                      </Typography.Text>
                    </div>
                  </div>
                ) : result.error ? (
                  <div className="all-timeframe-value">
                    <Tag color="error">Unavailable</Tag>
                  </div>
                ) : (
                  <Skeleton.Input active size="small" style={{ width: 120, marginTop: 8 }} />
                )}
              </Card>
            </Col>
          )
        })}
      </Row>
      {rows.length === 0 ? (
        <Card><Skeleton active paragraph={{ rows: 6 }} aria-label="Loading all timeframes" /></Card>
      ) : (
        <Table<MatrixRow>
          rowKey="symbol"
          columns={columns}
          dataSource={rows}
          pagination={false}
          size="small"
          className="market-table all-timeframes-table"
          aria-label="All timeframes market instruments"
        />
      )}
    </section>
  )
}
