import { Card, Col, Row, Typography } from 'antd'

import type { MultiTimeframeAnalysis, ScreenDecision } from '../../api/client'
import { decisionTone } from './mtfFormat'

function DecisionCard({ decision, headline = false }: { decision: ScreenDecision; headline?: boolean }) {
  return (
    <Card
      size="small"
      className={`mtf-decision mtf-decision-${decisionTone(decision.decision)}${headline ? ' mtf-decision-headline' : ''}`}
    >
      <Typography.Text type="secondary" className="mtf-decision-name">{decision.name}</Typography.Text>
      <div className="mtf-decision-value">{decision.decision}</div>
      {decision.position_note && (
        <Typography.Text type="secondary" className="mtf-decision-note">
          If already in a position: {decision.position_note}
        </Typography.Text>
      )}
    </Card>
  )
}

export default function DecisionStrip({ analysis }: { analysis: MultiTimeframeAnalysis }) {
  const [primary, ...otherDoubles] = analysis.decisions.double_screens
  return (
    <section aria-label="Screen decisions" className="mtf-decisions">
      <Row gutter={[16, 16]}>
        {primary && (
          <Col xs={24} md={12} xl={6}>
            <DecisionCard decision={primary} headline />
          </Col>
        )}
        <Col xs={24} md={12} xl={6}>
          <DecisionCard decision={analysis.decisions.triple_screen} headline />
        </Col>
        {otherDoubles.map((decision) => (
          <Col key={decision.name} xs={24} md={12} xl={6}>
            <DecisionCard decision={decision} />
          </Col>
        ))}
      </Row>
      <Typography.Text type="secondary" className="mtf-disclaimer">{analysis.decisions.disclaimer}</Typography.Text>
    </section>
  )
}
