import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig, devices } from '@playwright/test'

const dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(dirname, '..')

// Database connection the auto-started backend should use. Defaults match the
// standard local Postgres; a CI job can override via POSTGRES_* env vars.
const BACKEND_ENV = {
  IS_LOCAL: 'true',
  LOCAL_BACKEND_PORT: '3001',
  POSTGRES_HOST: process.env.POSTGRES_HOST || 'localhost',
  POSTGRES_PORT: process.env.POSTGRES_PORT || '5432',
  POSTGRES_USER: process.env.POSTGRES_USER || 'test',
  POSTGRES_PASS: process.env.POSTGRES_PASS || 'test',
  POSTGRES_NAME: process.env.POSTGRES_NAME || 'test',
}

/**
 * End-to-end tests for the ACME Project Tracker (full-stack.md → Frontend
 * Testing → "End-to-End Tests: Test complete user workflows").
 *
 * `globalSetup` migrates + seeds the database, and `webServer` boots both the
 * frontend (Vite, :3000) and the backend (in-process Lambda runner, :3001), so
 * `npm run test:e2e` is fully self-contained — nothing needs to be running
 * first. Locally, already-running servers are reused; in CI they are started
 * fresh and torn down automatically.
 *
 * See frontend/README.md → "E2E testing" for prerequisites.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  globalSetup: './e2e/global-setup.js',
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'npm run dev',
      url: 'http://localhost:3000',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'python3 bin/local-dev-server.py',
      cwd: REPO_ROOT,
      env: BACKEND_ENV,
      url: 'http://localhost:3001/',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
