import { Card, Col, Row, Statistic, Tag, Typography } from 'antd'

import type { GlobalMarketSnapshot } from '../../api/client'

interface SentimentSummaryProps {
  snapshot: GlobalMarketSnapshot
}

const completenessColor = {
  complete: 'success',
  partial: 'warning',
  unavailable: 'error',
} as const

export default function SentimentSummary({ snapshot }: SentimentSummaryProps) {
  const { breadth } = snapshot
  return (
    <section aria-labelledby="breadth-heading">
      <div className="section-heading">
        <div>
          <Typography.Title id="breadth-heading" level={2}>
            Daily breadth
          </Typography.Title>
          <Typography.Text type="secondary">
            Evidence-only movement across {snapshot.watchlist_name}
          </Typography.Text>
        </div>
        <Tag color={completenessColor[snapshot.completeness]}>{snapshot.completeness.toUpperCase()}</Tag>
      </div>
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <Card size="small"><Statistic title="Advancing" value={breadth.advancing} styles={{ content: { color: '#34d399' } }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small"><Statistic title="Declining" value={breadth.declining} styles={{ content: { color: '#fb7185' } }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small"><Statistic title="Unchanged" value={breadth.unchanged} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small"><Statistic title="Unavailable" value={breadth.unavailable} styles={{ content: { color: '#fbbf24' } }} /></Card>
        </Col>
      </Row>
    </section>
  )
}
