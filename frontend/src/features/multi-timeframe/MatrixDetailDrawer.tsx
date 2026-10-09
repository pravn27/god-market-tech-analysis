import { Descriptions, Drawer, Tag, Typography } from 'antd'

import type { MultiTimeframeAnalysis } from '../../api/client'
import { sourceColor, sourceLabel } from '../global-market/marketFormat'
import type { MatrixSelection } from './ChecklistMatrix'
import { biasColor, formatTimestamp, formatValue, signalColor, timeframeLabel } from './mtfFormat'

interface MatrixDetailDrawerProps {
  analysis: MultiTimeframeAnalysis
  selection: MatrixSelection | null
  onClose: () => void
}

function title(selection: MatrixSelection) {
  const layer = selection.kind === 'cell' ? selection.layer : selection.layer.name
  const label = selection.kind === 'cell' ? selection.row.label : `${selection.layer.screen_indicator} screen`
  return `${label} · ${layer} ${timeframeLabel[selection.timeframe]}`
}

export default function MatrixDetailDrawer({ analysis, selection, onClose }: MatrixDetailDrawerProps) {
  const status = selection ? analysis.timeframes[selection.timeframe] : undefined
  return (
    <Drawer open={selection !== null} title={selection ? title(selection) : 'Checklist detail'} onClose={onClose} size="default">
      {selection && (
        <>
          {selection.kind === 'cell' ? (
            <>
              <Typography.Paragraph>
                <Tag color={biasColor[selection.cell.bias]}>{selection.cell.bias.toUpperCase()}</Tag>
              </Typography.Paragraph>
              {selection.cell.unavailable_reason ? (
                <Typography.Paragraph>{selection.cell.unavailable_reason}</Typography.Paragraph>
              ) : (
                <ul className="mtf-drawer-labels">
                  {selection.cell.labels.map((label) => <li key={label}>{label}</li>)}
                </ul>
              )}
              {Object.keys(selection.cell.values).length > 0 && (
                <Descriptions
                  column={1}
                  size="small"
                  bordered
                  title="Values"
                  items={Object.entries(selection.cell.values).map(([key, value]) => ({
                    key,
                    label: key.replaceAll('_', ' '),
                    children: formatValue(value),
                  }))}
                />
              )}
              <Typography.Paragraph type="secondary" className="mtf-drawer-rules">
                Rules: {selection.cell.rule_ids.join(', ')} · profile {analysis.profile_version}
              </Typography.Paragraph>
            </>
          ) : (
            <>
              <Typography.Paragraph>
                <Tag color={signalColor[selection.screen.signal]}>{selection.screen.signal}</Tag>
              </Typography.Paragraph>
              {selection.screen.unavailable_reason && (
                <Typography.Paragraph>{selection.screen.unavailable_reason}</Typography.Paragraph>
              )}
              <ul className="mtf-drawer-labels">
                {selection.screen.labels.map((label) => <li key={label}>{label}</li>)}
              </ul>
            </>
          )}
          {status && (
            <Descriptions
              column={1}
              size="small"
              bordered
              title="Timeframe data"
              className="mtf-drawer-status"
              items={[
                { key: 'source', label: 'Source', children: status.source ? <Tag color={sourceColor[status.source]}>{sourceLabel[status.source]}</Tag> : '—' },
                { key: 'candle', label: 'Latest candle', children: `${formatTimestamp(status.source_timestamp)}${status.live_candle ? ' (live, still forming)' : ''}` },
                { key: 'close', label: 'Last close', children: formatValue(status.last_close) },
                { key: 'count', label: 'Candles used', children: status.candle_count },
              ]}
            />
          )}
        </>
      )}
    </Drawer>
  )
}
