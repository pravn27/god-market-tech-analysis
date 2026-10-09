import { Tag, Tooltip } from 'antd'
import { Fragment } from 'react'

import type {
  AnalysisTimeframe,
  ChecklistCell,
  LayerSignal,
  MtfChecklistRow,
  MultiTimeframeAnalysis,
  TimeframeScreen,
} from '../../api/client'
import { biasColor, signalColor, timeframeLabel } from './mtfFormat'

export type MatrixSelection =
  | { kind: 'cell'; row: MtfChecklistRow; timeframe: AnalysisTimeframe; layer: string; cell: ChecklistCell }
  | { kind: 'screen'; layer: LayerSignal; timeframe: AnalysisTimeframe; screen: TimeframeScreen }

interface ChecklistMatrixProps {
  analysis: MultiTimeframeAnalysis
  onSelect: (selection: MatrixSelection) => void
}

const freshnessTag = {
  ready: { color: 'success', label: 'Fresh' },
  stale: { color: 'warning', label: 'Stale' },
  unavailable: { color: 'error', label: 'Unavailable' },
  not_configured: { color: 'error', label: 'Not configured' },
} as const

function sectionsOf(rows: MtfChecklistRow[]) {
  const sections: { name: string; rows: MtfChecklistRow[] }[] = []
  for (const row of rows) {
    const current = sections.at(-1)
    if (current?.name === row.section) current.rows.push(row)
    else sections.push({ name: row.section, rows: [row] })
  }
  return sections
}

function CellTags({ cell }: { cell: ChecklistCell }) {
  if (cell.bias === 'unavailable') {
    return <Tag variant="outlined" className="mtf-tag mtf-tag-unavailable">Unavailable</Tag>
  }
  return (
    <>
      {cell.labels.map((label) => (
        <Tag key={label} color={biasColor[cell.bias]} className="mtf-tag">{label}</Tag>
      ))}
    </>
  )
}

export default function ChecklistMatrix({ analysis, onSelect }: ChecklistMatrixProps) {
  const columns = analysis.layers.flatMap((layer) => layer.timeframes.map((timeframe) => ({ layer, timeframe })))
  const columnCount = columns.length + 1
  const sections = sectionsOf(analysis.rows)
  const firstSetupSection = sections.findIndex((section) => section.name.startsWith('5'))
  const screenIndex = firstSetupSection === -1 ? sections.length : firstSetupSection

  const screenRows = (
    <>
      <tr className="mtf-section-row">
        <th colSpan={columnCount} scope="rowgroup">4. Double &amp; Triple Screen decision</th>
      </tr>
      <tr>
        <th scope="row" className="mtf-sticky mtf-row-header">Screen signal per timeframe</th>
        {columns.map(({ layer, timeframe }) => {
          const screen = layer.screens[timeframe]
          if (!screen) return <td key={`${layer.name}-${timeframe}`} />
          return (
            <td key={`${layer.name}-${timeframe}`}>
              <button
                type="button"
                className="mtf-cell"
                aria-label={`${layer.name} ${timeframeLabel[timeframe]} screen: ${screen.signal}`}
                onClick={() => onSelect({ kind: 'screen', layer, timeframe, screen })}
              >
                <Tag color={signalColor[screen.signal]} className="mtf-tag mtf-signal">{screen.signal}</Tag>
                {screen.labels.map((label) => <Tag key={label} className="mtf-tag">{label}</Tag>)}
              </button>
            </td>
          )
        })}
      </tr>
      <tr>
        <th scope="row" className="mtf-sticky mtf-row-header">Layer signal</th>
        {analysis.layers.map((layer) => (
          <td key={layer.name} colSpan={layer.timeframes.length} className="mtf-layer-signal">
            <Tag color={signalColor[layer.signal]} className="mtf-tag mtf-signal">{layer.signal}</Tag>
          </td>
        ))}
      </tr>
    </>
  )

  return (
    <div className="mtf-matrix-scroll" role="region" aria-label="Multi-timeframe checklist" tabIndex={0}>
      <table className="mtf-matrix">
        <thead>
          <tr>
            <th rowSpan={2} scope="col" className="mtf-sticky mtf-row-header">Checklist</th>
            {analysis.layers.map((layer) => (
              <th key={layer.name} colSpan={layer.timeframes.length} scope="colgroup" className="mtf-layer-header">
                {layer.name}
                <span className="mtf-layer-indicator">{layer.screen_indicator}</span>
              </th>
            ))}
          </tr>
          <tr>
            {columns.map(({ layer, timeframe }) => {
              const status = analysis.timeframes[timeframe]
              const freshness = freshnessTag[status?.freshness_state ?? 'unavailable']
              return (
                <th key={`${layer.name}-${timeframe}`} scope="col" className="mtf-tf-header">
                  <div className="mtf-tf-name">{timeframeLabel[timeframe]}</div>
                  <div className="mtf-tf-tags">
                    <Tooltip title={status?.unavailable_reason ?? undefined}>
                      <Tag color={freshness.color} className="mtf-tag">{freshness.label}</Tag>
                    </Tooltip>
                    {status?.live_candle && <Tag color="processing" className="mtf-tag">Live candle</Tag>}
                  </div>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sections.map((section, index) => (
            <Fragment key={section.name}>
              {index === screenIndex && screenRows}
              <tr className="mtf-section-row">
                <th colSpan={columnCount} scope="rowgroup">{section.name}</th>
              </tr>
              {section.rows.map((row) => (
                <tr key={row.id}>
                  <th scope="row" className="mtf-sticky mtf-row-header">{row.label}</th>
                  {columns.map(({ layer, timeframe }) => {
                    const key = `${row.id}-${layer.name}-${timeframe}`
                    if (!row.automated) {
                      return (
                        <td key={key}>
                          <Tag variant="filled" className="mtf-tag mtf-manual">Manual check</Tag>
                        </td>
                      )
                    }
                    const cell = row.cells[timeframe]
                    if (!cell) return <td key={key} />
                    return (
                      <td key={key}>
                        <button
                          type="button"
                          className={`mtf-cell mtf-cell-${cell.bias}`}
                          aria-label={`${row.label}, ${layer.name} ${timeframeLabel[timeframe]}: ${cell.labels.join(', ') || 'unavailable'}`}
                          onClick={() => onSelect({ kind: 'cell', row, timeframe, layer: layer.name, cell })}
                        >
                          <CellTags cell={cell} />
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </Fragment>
          ))}
          {screenIndex === sections.length && screenRows}
        </tbody>
      </table>
    </div>
  )
}
