import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 3000
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.js'],
    css: false,
    // v8 coverage instrumentation adds real per-statement overhead — the
    // default 5000ms is too tight for MUI-heavy dialog tests once coverage
    // is on, even though the same tests run in well under 1s without it.
    testTimeout: 20000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/main.jsx', 'src/**/*.test.{js,jsx}'],
    },
  },
})
