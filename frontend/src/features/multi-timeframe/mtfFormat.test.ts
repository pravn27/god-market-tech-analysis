import { describe, expect, it } from 'vitest'

import { formatValue } from './mtfFormat'

describe('formatValue', () => {
  it('renders boolean checklist evidence as readable text', () => {
    expect(formatValue(true)).toBe('Yes')
    expect(formatValue(false)).toBe('No')
  })
})
