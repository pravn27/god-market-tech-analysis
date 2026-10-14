import { describe, expect, it } from 'vitest'

import { formatValue, labelColor } from './mtfFormat'

describe('formatValue', () => {
  it('renders boolean checklist evidence as readable text', () => {
    expect(formatValue(true)).toBe('Yes')
    expect(formatValue(false)).toBe('No')
  })
})

describe('labelColor', () => {
  it('colours EMA price relations green above the EMA and red below it', () => {
    expect(labelColor('emas', 'Price > 26', 'neutral')).toBe('success')
    expect(labelColor('emas', 'Price < 26', 'bullish')).toBe('error')
  })

  it('keeps the cell bias colour for other EMA labels', () => {
    expect(labelColor('emas', 'POC, 5 > 13 > 26', 'bullish')).toBe('success')
    expect(labelColor('emas', 'EMAs intermingled', 'neutral')).toBe('default')
  })

  it('does not apply the price-relation colour outside the EMA row', () => {
    expect(labelColor('macd', 'Price > 26', 'bearish')).toBe('error')
    expect(labelColor('bb', 'Price > 26', 'neutral')).toBe('default')
  })
})
