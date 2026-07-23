import { cleanup } from '@testing-library/react'
import { afterEach, expect } from 'vitest'
import * as matchers from '@testing-library/jest-dom/matchers'

expect.extend(matchers)

// jsdom doesn't implement matchMedia — MUI's useMediaQuery (AppLayout's
// mobile nav, responsive breakpoints elsewhere) throws without it. Default
// to "no query matches" so components render their desktop/default layout
// unless a test explicitly overrides window.matchMedia for a mobile case.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}

// Without `test.globals: true` in vite.config.js, @testing-library/react's
// own auto-cleanup (which hooks into a global afterEach) never registers —
// component trees from earlier tests would otherwise pile up in the DOM.
afterEach(() => {
  cleanup()
})
