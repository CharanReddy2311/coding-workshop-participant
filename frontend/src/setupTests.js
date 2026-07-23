import { cleanup } from '@testing-library/react'
import { afterEach, expect } from 'vitest'
import * as matchers from '@testing-library/jest-dom/matchers'

expect.extend(matchers)

// Without `test.globals: true` in vite.config.js, @testing-library/react's
// own auto-cleanup (which hooks into a global afterEach) never registers —
// component trees from earlier tests would otherwise pile up in the DOM.
afterEach(() => {
  cleanup()
})
