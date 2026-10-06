import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => cleanup())

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return false },
  }),
})

Object.defineProperty(window, 'ResizeObserver', { writable: true, value: ResizeObserver })
Object.defineProperty(globalThis, 'ResizeObserver', { writable: true, value: ResizeObserver })

const nativeGetComputedStyle = window.getComputedStyle
window.getComputedStyle = ((element: Element) => nativeGetComputedStyle(element)) as typeof window.getComputedStyle
