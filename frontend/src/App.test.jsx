import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'

import App from './App'

beforeEach(() => {
  localStorage.clear()
  window.history.pushState({}, '', '/')
})

it('routes an unauthenticated visitor to the login screen', async () => {
  render(<App />)
  expect(await screen.findByText('ACME Project Tracker')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Sign In' })).toBeInTheDocument()
})

it('sends an unknown path through the same unauthenticated redirect', async () => {
  window.history.pushState({}, '', '/does-not-exist')
  render(<App />)
  expect(await screen.findByRole('button', { name: 'Sign In' })).toBeInTheDocument()
})
