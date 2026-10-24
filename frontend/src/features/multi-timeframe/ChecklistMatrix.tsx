import { DoubleLeftOutlined, DoubleRightOutlined, DownOutlined, RightOutlined } from '@ant-design/icons'
import { Button, Tag, Tooltip } from 'antd'
import { Fragment, useState } from 'react'

import type {
  AnalysisTimeframe,
  ChecklistCell,
  LayerSignal,
  MtfChecklistRow,
  MultiTimeframeAnalysis,
  TimeframeScreen,
} from '../../api/client'
import { biasWord, labelColor, signalColor, timeframeLabel } from './mtfFormat'

export type MatrixSelection =
  | { kind: 'cell'; row: MtfChecklistRow; timeframe: AnalysisTimeframe; layer: string; cell: ChecklistCell }
  | { kind: 'screen'; layer: LayerSignal; timeframe: AnalysisTimeframe; screen: TimeframeScreen }

interface ChecklistMatrixProps {
  analysis: MultiTimeframeAnalysis
  onSelect: (selection: MatrixSelection) => void
}

// Every layer can be collapsed. Super TIDE is used only when needed, so it starts collapsed.
const DEFAULT_COLLAPSED_LAYERS = ['Super TIDE']

const freshnessTag = {
  ready: { color: 'success', label: 'Fresh' },
  stale: { color: 'warning', label: 'Stale' },
  unavailable: { color: 'error', label: 'Unavailable' },
  not_configured: { color: 'error', label: 'Not configured' },
} as const

// One rendered column. A collapsed layer contributes a single placeholder slot (timeframe === null).
interface MatrixSlot {
  key: string
  layer: LayerSignal
  timeframe: AnalysisTimeframe | null
  layerStart: boolean
}

function buildSlots(layers: LayerSignal[], collapsed: Set<string>): MatrixSlot[] {
  return layers.flatMap((layer): MatrixSlot[] => {
    if (collapsed.has(layer.name)) {
      return [{ key: `${layer.name}-collapsed`, layer, timeframe: null, layerStart: true }]
    }
    return layer.timeframes.map((timeframe, index) => ({
      key: `${layer.name}-${timeframe}`,
      layer,
      timeframe,
      layerStart: index === 0,
    }))
  })
}

function sectionsOf(rows: MtfChecklistRow[]) {
  const sections: { name: string; rows: MtfChecklistRow[] }[] = []
  for (const row of rows) {
    const current = sections.at(-1)
    if (current?.name === row.section) current.rows.push(row)
    else sections.push({ name: row.section, rows: [row] })
  }
  return sections
}

const SCREEN_SECTION_NAME = '4. Double & Triple Screen decision'

function SectionHeading({
  name,
  columnCount,
  collapsed,
  onToggle,
}: {
  name: string
  columnCount: number
  collapsed: boolean
  onToggle: () => void
}) {
  return (
    <tr className="mtf-section-row">
      <th colSpan={columnCount} scope="rowgroup">
        <button
          type="button"
          className="mtf-section-toggle"
          aria-label={`${collapsed ? 'Expand' : 'Collapse'} section ${name}`}
          aria-expanded={!collapsed}
          onClick={onToggle}
        >
          {collapsed ? <RightOutlined /> : <DownOutlined />}
          <span>{name}</span>
        </button>
      </th>
    </tr>
  )
}

// Rows whose tags carry their own direction (each label has its bias word).
const BIAS_WORD_ROWS = new Set(['price_action', 'significant_candle'])

function CellTags({ rowId, cell }: { rowId: string; cell: ChecklistCell }) {
  if (cell.bias === 'unavailable') {
    return <Tag variant="outlined" className="mtf-tag mtf-tag-unavailable">Unavailable</Tag>
  }
  return (
    <>
      {cell.labels.map((label) => {
        const labelBias = cell.label_bias?.[label] ?? cell.bias
        const text = BIAS_WORD_ROWS.has(rowId) ? `${label} - ${biasWord[labelBias]}` : label
        return (
          <Tag key={label} color={labelColor(rowId, label, labelBias)} className="mtf-tag">{text}</Tag>
        )
      })}
    </>
  )
}

export default function ChecklistMatrix({ analysis, onSelect }: ChecklistMatrixProps) {
  const [collapsedLayers, setCollapsedLayers] = useState<Set<string>>(() => new Set(DEFAULT_COLLAPSED_LAYERS))
  // Sections start expanded; collapsing one hides its checklist rows only.
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(() => new Set())
  const slots = buildSlots(analysis.layers, collapsedLayers)
  const columnCount = slots.length + 1
  const sections = sectionsOf(analysis.rows)
  const firstSetupSection = sections.findIndex((section) => section.name.startsWith('5'))
  const screenIndex = firstSetupSection === -1 ? sections.length : firstSetupSection

  const toggleLayer = (name: string) => {
    setCollapsedLayers((previous) => {
      const next = new Set(previous)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const toggleSection = (name: string) => {
    setCollapsedSections((previous) => {
      const next = new Set(previous)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const screenCollapsed = collapsedSections.has(SCREEN_SECTION_NAME)
  const screenRows = (
    <>
      <SectionHeading
        name={SCREEN_SECTION_NAME}
        columnCount={columnCount}
        collapsed={screenCollapsed}
        onToggle={() => toggleSection(SCREEN_SECTION_NAME)}
      />
      {!screenCollapsed && (
        <>
        <tr>
          <th scope="row" className="mtf-sticky mtf-row-header">Screen signal per timeframe</th>
          {slots.map((slot) => {
            const startClass = slot.layerStart ? 'mtf-layer-start' : undefined
            const { layer, timeframe } = slot
            if (timeframe === null) return <td key={slot.key} className={`mtf-collapsed-col ${startClass ?? ''}`} aria-hidden="true" />
            const screen = layer.screens[timeframe]
            if (!screen) return <td key={slot.key} className={startClass} />
            return (
              <td key={slot.key} className={startClass}>
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
          {analysis.layers.map((layer) => {
            const collapsed = collapsedLayers.has(layer.name)
            return (
              <td
                key={layer.name}
                colSpan={collapsed ? 1 : layer.timeframes.length}
                className="mtf-layer-signal mtf-layer-start"
              >
                <Tag color={signalColor[layer.signal]} className="mtf-tag mtf-signal">{layer.signal}</Tag>
              </td>
            )
          })}
        </tr>
        </>
      )}
    </>
  )

  return (
    <div className="mtf-matrix-scroll" role="region" aria-label="Multi-timeframe checklist" tabIndex={0}>
      <table className="mtf-matrix">
        <colgroup>
          <col className="mtf-col-label" />
          {slots.map((slot) => (
            <col key={slot.key} className={slot.timeframe === null ? 'mtf-col-collapsed' : undefined} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <th rowSpan={2} scope="col" className="mtf-sticky mtf-row-header">Checklist</th>
            {analysis.layers.map((layer) => {
              if (collapsedLayers.has(layer.name)) {
                return (
                  <th key={layer.name} scope="colgroup" className="mtf-layer-header mtf-layer-collapsed mtf-layer-start">
                    <Tooltip title={`Expand ${layer.name}`}>
                      <Button
                        type="text"
                        size="small"
                        className="mtf-layer-toggle"
                        icon={<DoubleRightOutlined />}
                        aria-label={`Expand ${layer.name} column`}
                        aria-expanded={false}
                        onClick={() => toggleLayer(layer.name)}
                      />
                    </Tooltip>
                    <span className="mtf-layer-collapsed-name">{layer.name}</span>
                  </th>
                )
              }
              return (
                <th
                  key={layer.name}
                  colSpan={layer.timeframes.length}
                  scope="colgroup"
                  className="mtf-layer-header mtf-layer-start"
                >
                  <span className="mtf-layer-title">{layer.name}</span>
                  <span className="mtf-layer-indicator">{layer.screen_indicator}</span>
                  <Tooltip title={`Collapse ${layer.name}`}>
                    <Button
                      type="text"
                      size="small"
                      className="mtf-layer-toggle"
                      icon={<DoubleLeftOutlined />}
                      aria-label={`Collapse ${layer.name} column`}
                      aria-expanded
                      onClick={() => toggleLayer(layer.name)}
                    />
                  </Tooltip>
                </th>
              )
            })}
          </tr>
          <tr>
            {slots.map((slot) => {
              const startClass = slot.layerStart ? 'mtf-layer-start' : undefined
              if (slot.timeframe === null) return <th key={slot.key} aria-hidden="true" className={`mtf-collapsed-col ${startClass ?? ''}`} />
              const status = analysis.timeframes[slot.timeframe]
              const freshness = freshnessTag[status?.freshness_state ?? 'unavailable']
              return (
                <th key={slot.key} scope="col" className={`mtf-tf-header ${startClass ?? ''}`}>
                  <div className="mtf-tf-name">{timeframeLabel[slot.timeframe]}</div>
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
              <SectionHeading
                name={section.name}
                columnCount={columnCount}
                collapsed={collapsedSections.has(section.name)}
                onToggle={() => toggleSection(section.name)}
              />
              {!collapsedSections.has(section.name) && section.rows.map((row) => (
                <tr key={row.id}>
                  <th scope="row" className="mtf-sticky mtf-row-header">{row.label}</th>
                  {slots.map((slot) => {
                    const startClass = slot.layerStart ? 'mtf-layer-start' : undefined
                    const key = `${row.id}-${slot.key}`
                    const { layer, timeframe } = slot
                    if (timeframe === null) return <td key={key} className={`mtf-collapsed-col ${startClass ?? ''}`} aria-hidden="true" />
                    if (!row.automated) {
                      return (
                        <td key={key} className={startClass}>
                          <Tag variant="filled" className="mtf-tag mtf-manual">Manual check</Tag>
                        </td>
                      )
                    }
                    const cell = row.cells[timeframe]
                    if (!cell) return <td key={key} className={startClass} />
                    return (
                      <td key={key} className={startClass}>
                        <button
                          type="button"
                          className={`mtf-cell mtf-cell-${cell.bias}`}
                          aria-label={`${row.label}, ${layer.name} ${timeframeLabel[timeframe]}: ${cell.labels.join(', ') || 'unavailable'}`}
                          onClick={() => onSelect({ kind: 'cell', row, timeframe, layer: layer.name, cell })}
                        >
                          <CellTags rowId={row.id} cell={cell} />
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
