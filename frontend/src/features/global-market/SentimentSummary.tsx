import { ArrowDownOutlined, ArrowUpOutlined, FallOutlined, MinusOutlined, RiseOutlined } from '@ant-design/icons'
import { Card, Col, Progress, Row, Statistic, Tag, Typography } from 'antd'
import type { ReactNode } from 'react'

import type { GlobalMarketSnapshot } from '../../api/client'
import { marketColors } from '../../theme'
import { calculateSentiment, NEUTRAL_BAND_PERCENT, sentimentTagColor, type SentimentLabel } from './marketFormat'

interface SentimentSummaryProps {
  snapshot: GlobalMarketSnapshot
}

const labelColor: Record<SentimentLabel, string> = {
  Bullish: marketColors.bullish,
  Neutral: marketColors.neutral,
  Bearish: marketColors.bearish,
}

const labelIcon: Record<SentimentLabel, ReactNode> = {
  Bullish: <RiseOutlined />,
  Neutral: <MinusOutlined />,
  Bearish: <FallOutlined />,
}

export default function SentimentSummary({ snapshot }: SentimentSummaryProps) {
  const sentiment = calculateSentiment(snapshot.groups.flatMap((group) => group.instruments))
  const { dominantLabel, dominantPercent, total } = sentiment
  const color = labelColor[dominantLabel]
  const share = (count: number) => (total > 0 ? Math.round((count / total) * 100) : 0)
  const breakdown: { label: SentimentLabel; count: number; icon?: ReactNode }[] = [
    { label: 'Bullish', count: sentiment.bullish, icon: <ArrowUpOutlined /> },
    { label: 'Neutral', count: sentiment.neutral },
    { label: 'Bearish', count: sentiment.bearish, icon: <ArrowDownOutlined /> },
  ]

  return (
    <section aria-label="Market sentiment">
      <Row gutter={[16, 16]}>
        <Col xs={24} md={9}>
          <Card className={`sentiment-dominant sentiment-dominant-${dominantLabel.toLowerCase()}`}>
            <Typography.Text type="secondary" className="sentiment-caption">Dominant Sentiment</Typography.Text>
            <div className="sentiment-dominant-value">
              <Statistic
                value={dominantPercent}
                suffix="%"
                prefix={labelIcon[dominantLabel]}
                styles={{ content: { color, fontSize: 40, fontWeight: 700 } }}
              />
              <Tag color={sentimentTagColor[dominantLabel]} className="sentiment-dominant-tag">
                {dominantLabel.toUpperCase()}
              </Tag>
            </div>
            <Progress percent={dominantPercent} showInfo={false} strokeColor={color} size={['100%', 10]} />
            <Typography.Text type="secondary" className="sentiment-footnote">
              Based on {total} instruments across {snapshot.groups.length} sections
              {sentiment.unavailable > 0 && ` · ${sentiment.unavailable} unavailable`}
              {' '}· neutral band ±{NEUTRAL_BAND_PERCENT}%
            </Typography.Text>
          </Card>
        </Col>
        {breakdown.map(({ label, count, icon }) => (
          <Col xs={8} md={5} key={label}>
            <Card className="sentiment-breakdown" style={{ borderTopColor: labelColor[label] }}>
              <Statistic
                title={<Typography.Text strong>{label}</Typography.Text>}
                value={count}
                prefix={icon}
                styles={{ content: { color: labelColor[label], fontSize: 32, fontWeight: 700 } }}
              />
              <Typography.Text type="secondary" className="sentiment-footnote">{share(count)}% of markets</Typography.Text>
            </Card>
          </Col>
        ))}
      </Row>
    </section>
  )
}
